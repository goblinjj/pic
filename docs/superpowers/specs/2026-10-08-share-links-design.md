# 只读分享链接 — 设计文档

日期：2026-10-08
状态：待实现

## 背景

多用户上线后，每个账号的数据完全隔离，别人想看只能登录同一个账号。现在要让用户
把自己的内容以只读方式分享给别人，对方打开链接即可浏览，不需要账号、不需要登录。

## 目标

1. 用户可以为**某个分类**或**整个账号**生成分享链接
2. 访客打开链接后可以：浏览日志列表、查看详情（含原图）、文字搜索、按状态与自定义
   字段筛选、按字段排序、以图搜图；账号级分享还能按分类筛选
3. 访客看不到也调用不到任何写操作
4. 链接永久有效，直到用户手动撤销；同一范围可以有多条链接，各自独立撤销
5. 分类级分享严格限制在该分类内：其他分类的日志、图片、搜索结果一概拿不到

## 非目标

- 单条日志分享
- 过期时间、访问密码、访问次数统计
- 访客评论或任何形式的写入
- 管理后台查看 / 撤销别人的分享链接
- 分享范围的部分字段隐藏（主人能看到的，访客都能看到）

## 方案选择

| 方案 | 结论 |
| --- | --- |
| **A. 独立的只读分享 API `/api/share/{token}/...` + 前端只读模式** | **采用**。分享路径上只有 GET 和以图搜图，写接口根本不存在；范围检查集中在一个依赖和一个路由文件里，便于审查 |
| B. 现有接口额外接受分享 token 作为认证 | 放弃。现有接口没有「分类范围」概念，`GET /api/logs/{id}`、`/api/files/...` 等都要逐个补检查，漏一处分类级分享就退化成整个账号 |
| C. 服务端渲染静态 HTML | 放弃。要另写一套 UI，也做不了筛选和以图搜图 |

## 数据

`accounts.db` 新增一张表（访客没有会话，必须能从 token 直接找到账号，只能放在
各账号库之外）。在 `accounts.init_schema()` 里 `CREATE TABLE IF NOT EXISTS`，
老库启动时自动建表，无需迁移脚本。

```sql
CREATE TABLE IF NOT EXISTS shares (
    token       TEXT PRIMARY KEY,      -- secrets.token_urlsafe(24)，32 个字符
    user_id     INTEGER NOT NULL,
    category_id INTEGER,               -- NULL = 整个账号
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_shares_user ON shares(user_id);
```

- **token 明文存储**：用户要在「我的分享」里随时复制已有链接。拿到 `accounts.db`
  的人本来就能读到同目录下所有账号的库，哈希不提供额外保护
- `category_id` 指向该账号自己库里的 `categories.id`，跨库无法建外键，
  有效性在每次访问时检查（见下）
- 删除分类时顺带删除指向它的分享（`categories.py` 的 `delete_category`
  里调用 `accounts.delete_shares_for_category(user_id, category_id)`）。
  即便漏删，访问时的有效性检查也会让它返回 404

`accounts.py` 新增函数：

```python
create_share(conn, user_id, category_id: int | None) -> str   # 返回 token
list_shares(conn, user_id) -> list[Row]                        # 按 created_at 倒序
delete_share(conn, user_id, token) -> bool                     # 只能删自己的
delete_shares_for_category(conn, user_id, category_id)
resolve_share(conn, token) -> Row | None   # JOIN users，账号停用时返回 None
```

## 后端：主人侧接口（需登录）

新文件 `backend/routers/shares.py`，前缀 `/api/shares`，全部依赖 `current_user`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/shares` | 列出自己的分享：`token, category_id, category_name, created_at`。`category_name` 从当前账号库查；分类已不存在的条目照样列出，名称显示为空，方便撤销 |
| POST | `/api/shares` | body `{category_id: int \| null}`。`category_id` 非空时校验分类存在于自己的库，否则 400。返回新建的条目 |
| DELETE | `/api/shares/{token}` | 只删 `user_id` 等于自己的；不存在或不是自己的都返回 404 |

## 后端：访客侧接口（无需登录）

新文件 `backend/routers/public_share.py`，前缀 `/api/share/{token}`。

### 范围解析依赖

`deps.py` 新增：

```python
class ShareScope(NamedTuple):
    user_id: int
    category_id: int | None
    db: sqlite3.Connection
    upload_dir: str

def share_scope(token: str) -> Iterator[ShareScope]:
    # 1. accounts.resolve_share(token)；不存在 / 账号停用 → 404
    # 2. 打开该账号的库（库文件不存在 → 404，不是 500：访客不该知道内部状态）
    # 3. category_id 非空时确认分类仍存在，否则 404
    # 4. yield，结束时关闭连接
```

所有失败统一 `404 "分享链接不存在或已失效"`，不区分原因，避免探测。
该依赖**不读取 Cookie**，访客已登录与否对结果没有影响。

### 范围条件

`public_share.py` 内一个函数产出范围 SQL，所有查询都要拼上：

```python
def scope_clause(scope) -> tuple[list[str], list]:
    where = ["l.deleted_at IS NULL"]
    params = []
    if scope.category_id is not None:
        where.append("l.category_id = ?")
        params.append(scope.category_id)
    return where, params
```

### 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/info` | `{scope: "account" \| "category", category_id, category_name, owner}`；`owner` 为用户名，用于页面标题「xx 分享的…」；`category_id` 供前端锁定分类筛选 |
| GET | `/categories` | 账号级：全部分类；分类级：只返回该分类 |
| GET | `/categories/{cid}/fields` | 字段与选项，用于筛选和排序。分类级分享下 `cid` 不等于分享的分类 → 404 |
| GET | `/logs` | 参数与 `/api/logs` 相同（`search, category_id, status, fv, sort, page, size`），另限制 `page ≥ 1`、`1 ≤ size ≤ 100`，越界 422（匿名接口不能一次拉全库）。分类级分享下传入其他 `category_id` 得到空列表（范围条件与之 AND） |
| GET | `/logs/{log_id}` | 详情；不在范围内 → 404 |
| GET | `/files/{filename}`、`/files/thumbs/{filename}` | 文件名须登记在 images 表，**且**所属日志满足范围条件（未删除、分类匹配） |
| POST | `/search/image` | 以图搜图，结果限定在范围内；按 IP 限流 |

实现上复用 `routers/logs.py` 的 `LOG_COLUMNS`、`_build_log`、`_build_log_list`，
`field_values.py` 的 `build_option_filters`、`build_sort`；`/logs` 的查询拼装从
`list_logs` 抽成一个接受额外 where 条件的函数，两边共用，避免两份筛选逻辑走样。
以图搜图同理，把 `search.py` 里「读图 → 推理 → 组装结果」抽成共用函数。

**文件缓存头**：分享路径下的图片同样 `private, max-age=31536000`。撤销后已缓存在
访客浏览器里的图片仍能看到，这是可接受的（他们本来就看过了）。

### 以图搜图

- `image_search.rank_logs` 增加可选参数 `category_id`，非空时 SQL 加
  `AND l.category_id = ?`。登录用户的调用不传，行为不变
- 返回中的 `pending`（未建索引数）对访客没有意义，固定返回 0，`indexed` 照常
- 限流：`ratelimit.py` 现有的是「连续失败锁定」，语义不同。新增一个简单的滑动窗口
  计数器 `ratelimit.hit(key, limit, window_seconds) -> bool`，key 为
  `("share_search", ip)`，每 IP 每分钟 10 次，超出返回 429 `"搜索太频繁，请稍后再试"`。
  同样只放进程内存

## 前端

### 数据源抽象

`LogList`、`LogDetail`、`ImageSearch` 现在直接调用 `api.getLogs` 等。改为通过
`inject('source')` 取数据源，默认（不 provide 时）就是现有 `api`，主人侧行为不变。

新文件 `frontend/src/shareApi.js`：

```js
export function createShareSource(token) {
  return {
    readonly: true,
    getInfo, getCategories, getCategoryFields, getLogs, getLog, searchByImage,
    thumbUrl(filename), fileUrl(filename),
  }
}
```

- 请求**不带** `X-PicLog-User`，401/404 不跳登录页，而是抛出带 `status` 的错误
- `thumbs.js` 的 `thumbUrl` 也挪进数据源：主人侧是 `/api/files/thumbs/...`，
  分享侧是 `/api/share/{token}/files/thumbs/...`。组件里所有拼图片地址的地方改用
  `source.thumbUrl` / `source.fileUrl`
- `imageSearch.js` 的模块级状态改为按数据源区分（`searchByPhoto(file, source)`），
  避免主人和分享页的结果互相串

### 路由

```js
{
  path: '/s/:token',
  component: ShareLayout,          // provide('source', createShareSource(token))
  meta: { public: true, share: true },
  children: [
    { path: '', name: 'ShareList', component: LogList, children: [
      { path: 'logs/:id(\\d+)', name: 'ShareDetail', component: LogDetail },
    ]},
    { path: 'search/image', name: 'ShareImageSearch', component: ImageSearch, children: [
      { path: 'logs/:id(\\d+)', name: 'ShareImageSearchDetail', component: LogDetail },
    ]},
  ],
}
```

- 路由守卫：`meta.share` 的路由**不调用** `ensureSession`、不重定向，已登录用户打开
  分享链接看到的也是分享页
- `App.vue` 现在按 `meta.public` 隐藏 TopBar/BottomNav，分享页同样隐藏，由
  `ShareLayout` 自己显示一个简单的顶栏：「{owner} 分享的{分类名 / 全部内容}」
- 组件内部跳转（打开详情、去以图搜图）目前写死了路由名或路径，改为按当前是否
  在分享布局下选择对应的路由名

### 只读模式

`source.readonly` 为真时：

- `LogList`：隐藏新建按钮；账号级显示分类筛选，分类级隐藏分类筛选
- `LogDetail`：隐藏编辑、删除、改状态、上传图片、删除图片；外部链接照常可点
- `LogCard`：状态徽章只展示，不可点
- 不显示 BottomNav，所以分类管理、字段配置无入口

### 失效页

`/info` 返回 404 时，`ShareLayout` 显示「分享链接不存在或已失效」，不渲染子路由。

### 主人侧管理

- `Categories.vue` 每个分类一行加「分享」按钮；页面顶部加「分享全部」
- 点击后调用 `POST /api/shares`，弹出含完整链接的面板，带「复制」按钮
  （`navigator.clipboard`，不可用时选中文本让用户手动复制——NAS 走 http，
  非 localhost 下 clipboard API 不可用）
- 新页面 `Shares.vue`（路由 `/shares`，从分类页进入）：列出全部分享
  （范围、创建时间、复制、撤销）。撤销前 `confirm` 确认

## 错误处理

| 情况 | 访客看到 |
| --- | --- |
| token 不存在 / 已撤销 / 账号停用 / 分类已删除 / 库文件缺失 | 失效页（统一 404） |
| 日志不在范围内或已删除 | 详情卡片显示「内容不存在」 |
| 以图搜图未启用 | 与主人侧相同的「未启用」提示（503） |
| 以图搜图被限流 | 「搜索太频繁，请稍后再试」（429） |

## 测试

后端（pytest，参照 `test_isolation.py`）：

1. `test_shares.py` — 主人侧：创建账号级 / 分类级、分类不存在 400、列表只含自己的、
   撤销别人的 404、删除分类时其分享被删除、未登录 401
2. `test_share_access.py` — 访客侧，**重点**：
   - 不带 Cookie 能访问全部只读接口
   - 分类级 token：其他分类的日志列表为空、详情 404、图片与缩略图 404、
     字段接口 404、以图搜图结果不含其他分类
   - 已软删除的日志：详情 404、图片 404
   - 撤销后、账号停用后、分类删除后：所有接口 404
   - A 账号的 token 拿不到 B 账号同 id 的日志和同名文件
   - 带着 B 账号的登录 Cookie 访问 A 的分享，看到的仍是 A 的数据
   - 分享前缀下不存在 PUT / PATCH / DELETE，以及除以图搜图之外的 POST（405/404）
   - 以图搜图超过每分钟 10 次返回 429
3. 现有测试全部通过（主人侧行为不变的回归保障）

前端：手动验证——主人侧所有页面行为不变；分享页在已登录 / 未登录、
账号级 / 分类级、失效链接四种情况下表现正确。
