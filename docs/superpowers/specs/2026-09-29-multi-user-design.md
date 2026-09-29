# 多用户与管理后台 — 设计文档

日期：2026-09-29
状态：待实现

## 背景

PicLog 目前是单用户应用：没有登录，所有人打开就是同一份数据，图片通过公开的
`/uploads/...` 直接访问。现在要让多人使用同一个部署，每人拥有完全独立的环境。

## 目标

1. 打开应用的第一个界面是登录页，输入账号和密码后才能进入
2. 每个账号的数据完全独立：分类、自定义字段、日志、图片文件、以图搜图索引互不可见
3. 没有自助注册；账号只能在管理后台创建和管理
4. 管理后台的入口是一条长且随机的路径，用户端代码里不出现它
5. 升级时自动创建第一个账号 `babelingz`，现有数据全部归到它名下，ID、文件名、
   特征向量都保持不变，不需要重算索引

## 非目标

- 删除账号
- 用户自己修改密码（由管理员重置）
- 用户之间共享数据
- 多个管理员
- 修改用户名

## 方案选择

| 方案 | 结论 |
| --- | --- |
| **A. 每个账号一个独立的 SQLite 库和上传目录** | **采用**。隔离在物理层面，现有 SQL 一行都不用改，不存在「漏写 `WHERE user_id` 导致泄露」这类风险 |
| B. 单一数据库，各表加 `user_id` | 放弃。要改约 1200 行路由里的全部查询，任何一处遗漏都是越权漏洞 |
| C. 每个账号一个容器 | 放弃。新增账号要改部署配置，与「在后台添加账号」冲突 |

## 存储结构

沿用 NAS 上现有的两个挂载卷，`docker-compose.yml` 的卷配置不变。

```
/app/data/
  accounts.db              新增：账号、会话、管理员、迁移记录
  models/dinov2-small.onnx 不变，所有用户共用
  users/<id>/piclog.db     每个账号一个库，表结构即现有的 init_db()
/app/uploads/
  users/<id>/<file>        原图
  users/<id>/thumbs/<file> 缩略图
```

`DATA_DIR` 取 `DB_PATH` 所在目录（保持现有环境变量兼容），`UPLOAD_DIR` 含义不变。

### accounts.db

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,       -- sha256(token)，明文 token 只在 Cookie 里
    user_id    INTEGER NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE admin (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    password_hash TEXT NOT NULL
);

CREATE TABLE admin_sessions (
    token_hash TEXT PRIMARY KEY,
    expires_at DATETIME NOT NULL
);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

密码哈希：`hashlib.scrypt`（n=2^14, r=8, p=1，16 字节随机盐），存为
`scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>`，比较用 `hmac.compare_digest`。
不引入新依赖。

### 新建账号

在 `users` 插入一行后，立即创建 `data/users/<id>/`、`uploads/users/<id>/thumbs/`，
并对新库执行 `init_db()`。

## 首次升级迁移

启动时在 `accounts.db` 建表之后执行。完成后写 `meta.legacy_migrated = 1`，
之后永不再跑。每一步都先检查源是否存在，中途中断后重启可以继续：

1. `users` 中没有账号时，创建 `babelingz`（id=1），密码取环境变量
   `INITIAL_USER_PASSWORD`；变量为空则**启动失败**并给出明确报错
2. 若 `data/piclog.db` 存在，把它及 `-wal`、`-shm` 移到 `data/users/1/`
3. 把 `uploads/` 根目录下的普通文件移到 `uploads/users/1/`，
   `uploads/thumbs/` 下的文件移到 `uploads/users/1/thumbs/`
4. 写迁移完成标记

全部使用同卷 `os.replace`，不复制。全新部署（没有旧库）只会创建空账号。

之后照常：对每个用户的库执行 `init_db()`（含现有的一次性迁移），对每个用户的
上传目录执行缩略图补全 `migrate_existing()`。

管理员密码：`admin` 表为空且 `ADMIN_PASSWORD` 非空时写入。之后修改环境变量
不会覆盖已有密码。

## 配置

写在 NAS 上的 `/volume2/homes/darlingz/pic/.env`（已在 `.gitignore` 中），
`docker-compose.yml` 通过 `env_file: .env` 读取：

| 变量 | 说明 |
| --- | --- |
| `ADMIN_PATH` | 管理后台路径前缀，形如 `console-<32 位随机小写字母数字>`，不含斜杠 |
| `ADMIN_PASSWORD` | 管理员初始密码，仅首次写入 |
| `INITIAL_USER_PASSWORD` | `babelingz` 的初始密码，仅首次写入 |

这三个值都不进入 git 仓库，也不写入本文档。

## 用户登录

### 接口（不需要登录）

- `POST /api/auth/login` `{username, password}` → 200 `{username}`，并设置 Cookie
- `POST /api/auth/logout` → 204，删除会话并清除 Cookie
- `GET /api/auth/me` → 200 `{username}` 或 401
- `GET /api/health` → 200，供 `deploy.sh` 健康检查使用

### 会话

- Cookie `piclog_session`：32 字节随机 token（`secrets.token_urlsafe`），
  设置 HttpOnly、SameSite=Lax、Path=/、Max-Age 30 天。NAS 走 http，所以不设 Secure
- 滑动续期：剩余有效期不足 29 天时，把 `expires_at` 延长到 30 天后，并重发 Cookie。
  这样每天最多写一次库
- 过期的会话在登录时顺带清理

### 失败处理

- 统一提示「账号或密码错误」，不区分账号不存在还是密码错误
- 账号已停用时也返回同样的提示
- 限流：同一 IP 对同一用户名连续失败 5 次后锁定 15 分钟（管理员登录按 IP），锁定期间返回 429。
  按 (IP, 用户名) 计数是因为 Docker 端口映射可能让所有客户端显示为同一网关 IP，
  只按 IP 会一人输错锁住所有人。
  计数只保存在进程内存里，登录成功后清零

## 请求隔离

新增 `auth.py`，提供以下依赖：

- `current_user(request)`：读取 Cookie → 按 sha256 查会话 → 检查未过期且账号为启用
  状态，否则返回 401
- `get_db`：替换 `database.get_db`，基于 `current_user` 打开
  `data/users/<id>/piclog.db`（WAL、外键设置与现在相同）
- `get_upload_dir`：返回 `uploads/users/<id>`

所有路由原本都通过 `Depends(get_db)` 获取连接，只需把 import 指向新的依赖。
`images.py`、`logs.py`、`thumbnail.py`、`indexer.py` 中写死的 `UPLOAD_DIR` / `THUMB_DIR`
改为接收目录参数。

### 图片文件

- 移除 `app.mount("/uploads", StaticFiles(...))`
- 新增 `GET /api/files/{filename}` 与 `GET /api/files/thumbs/{filename}`：需要登录，
  只从当前用户的目录读取。文件名必须等于当前用户库 `images.filename` 中登记过的某一项
  （且不含路径分隔），否则返回 404。旧数据的扩展名来自原始文件名、格式不统一，所以不用正则
- 响应头 `Cache-Control: private, max-age=31536000`：文件名是 uuid，内容不会变
- 前端 `thumbs.js` 改为 `/api/files/thumbs/<name>?v=`，`LogDetail.vue` 的原图改为
  `/api/files/<name>`

## 以图搜图

- 特征向量仍在各用户自己库的 `image_embeddings` 表中。搜索接口通过 `get_db`
  拿到的就是当前用户的库，因此只在自己的图片里比对。`image_search.py` 不变
- 仍然只有一个后台索引线程（J3455 较弱，不并发推理）。每次被唤醒时，依次处理每个
  **启用**账号：打开它的库，按现有的 `_missing` 查询补算，从该用户目录读取图片
- 解码失败集合 `_failed` 的键改为 `(user_id, image_id)`
- `count_pending(conn, user_id)` 相应增加参数
- 停用账号的图片暂停补算，重新启用后由下一轮扫描补上
- 模型全局只加载一次；模型缺失时的降级行为不变

## 管理后台

### 路由

仅当 `ADMIN_PATH` 与管理员密码都已就绪时注册；否则不注册任何后台路由，
启动日志给出警告。SPA 兜底路由对 `/{ADMIN_PATH}` 以外的路径行为不变。

- `GET /{ADMIN_PATH}/` → `backend/admin/index.html`
- `POST /{ADMIN_PATH}/api/login` `{username, password}`：`username` 必须为 `admin`
- `POST /{ADMIN_PATH}/api/logout`
- `GET /{ADMIN_PATH}/api/users` → `[{id, username, is_active, created_at, log_count, image_count}]`
- `POST /{ADMIN_PATH}/api/users` `{username, password}` → 201
- `PUT /{ADMIN_PATH}/api/users/{id}/password` `{password}` → 204，并删除该用户的全部会话
- `PUT /{ADMIN_PATH}/api/users/{id}/active` `{is_active}` → 204，停用时删除全部会话

`log_count` 统计该用户库中 `deleted_at IS NULL` 的日志数，`image_count` 统计图片数。
后台只能看到这两个数字，看不到具体内容。

### 会话

Cookie `piclog_admin`：Path=`/{ADMIN_PATH}`、HttpOnly、SameSite=Strict、有效期 12 小时，
不续期。登录限流规则与用户端相同，计数独立。

### 校验

- 用户名：`^[a-z0-9_]{3,32}$`，唯一，重复时返回 409
- 密码：至少 8 个字符，最多 128 个字符

### 页面

`backend/admin/index.html` 是单文件页面，使用原生 JS，没有构建步骤，不进入
`frontend/`，因此用户端的打包产物里不会出现 `ADMIN_PATH`。页面内的接口地址
用相对路径 `api/...`。页面包含：登录表单、用户列表（用户名、状态、创建时间、
日志数、图片数）、新建账号表单，以及每行的「重置密码」和「启用 / 停用」按钮。
样式与用户端保持一致的简洁风格，适配手机宽度。

## 前端（用户端）

- 新增 `views/Login.vue`，路由为 `/login`
- 全局 `beforeEach` 守卫：首次导航时调用 `/api/auth/me` 并缓存结果；未登录时跳转到
  `/login?redirect=<原路径>`。已登录时访问 `/login` 则跳回首页
- `api.js` 的 `request()` 收到 401 时清除登录缓存并跳转到 `/login`。登录接口本身的
  401 除外，它只需显示错误
- 顶栏增加「退出登录」入口，并显示当前用户名
- `LogList` 被 keep-alive 缓存着，切换账号时必须清空缓存：登出后执行
  `location.href = '/login'` 整页刷新

## 部署

- `docker-compose.yml` 增加 `env_file: .env`
- `deploy.sh` 的健康检查路径改为 `/api/health`
- `deploy.sh` 在重建容器前检查 NAS 上是否已有 `data/accounts.db`。没有则说明即将
  执行首次迁移，先把 `data/` 和 `uploads/` 用 `cp -a` 备份到
  `backups/pre-multiuser-<时间戳>/`；已有则跳过备份
- 上线前把 `.env` 放到 NAS 上；缺少 `INITIAL_USER_PASSWORD` 会导致启动失败，
  健康检查也就不会通过，部署脚本会中止并提示回滚命令

## 异常与边界

| 情况 | 行为 |
| --- | --- |
| 未配置 `ADMIN_PATH` 或管理员密码 | 后台整体禁用（返回 404），记录警告日志，应用其余部分正常 |
| 需要创建首个账号但 `INITIAL_USER_PASSWORD` 为空 | 启动失败，报错信息写明缺少的变量 |
| 某个用户的库打不开 | 该用户的请求返回 500 并记录日志；索引线程跳过该用户，继续处理下一个 |
| 会话对应的账号被停用 | 下次请求返回 401，前端跳转到登录页 |
| 用 A 的日志、图片 ID 以 B 的身份访问 | B 的库中不存在该 ID，返回 404 |

## 测试

`conftest.py`：

- 环境变量改为 `DB_PATH=<tmp>/data/piclog.db`，并设置 `INITIAL_USER_PASSWORD`、
  `ADMIN_PATH`、`ADMIN_PASSWORD`
- 每个测试前清空 `<tmp>/data` 和 `<tmp>/uploads`
- `client` fixture 以首个账号登录后返回，现有测试不需要修改
- `db_conn` fixture 打开 user 1 的库
- 新增 `login_as(username)` 工具与 `anon_client` fixture

新增测试：

- `test_auth.py`：登录成功与失败、登出、`me`、会话过期、滑动续期、停用后立即 401、
  重置密码后旧会话失效、第 6 次失败返回 429
- `test_isolation.py`：用户 A 创建分类、日志和图片后，B 的列表为空；B 用 A 的
  ID 访问日志、图片、字段、选项均返回 404；B 读取 A 的文件返回 404；搜图只返回
  自己的结果
- `test_files.py`：未登录 401、路径穿越和非法文件名 404、缩略图与原图正常返回
- `test_accounts_migration.py`：构造旧版目录（旧库和图片）后启动，数据全部落在
  user 1 下且 ID 不变；再次启动不会重复迁移；模拟中途中断（部分文件已移动）后
  重启能完成迁移；全新部署只创建空账号；缺少 `INITIAL_USER_PASSWORD` 时报错
- `test_admin.py`：未配置时后台路由 404；未登录 401；登录、建号（重名 409、非法
  用户名 400）、重置密码、启停；列表统计数字正确
- `test_indexer.py` 补充：两个用户各自的图片分别写入各自的库，不会串库；停用账号被跳过

用户端打包产物不含后台路径是结构上保证的：`ADMIN_PATH` 只存在于 NAS 的 `.env`，
前端构建时根本拿不到它，因此不另做构建检查。
