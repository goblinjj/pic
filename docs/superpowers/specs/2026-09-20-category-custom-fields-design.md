# 分类绑定自定义字段 — 设计文档

日期：2026-09-20
状态：待实现

## 背景

PicLog 当前把日志字段硬编码在五个地方：`database.py` 的建表语句、`models.py` 的
`LogOut` / `LogUpdate`、`logs.py` 的全部 SQL、`LogForm.vue`、`LogDetail.vue`。
新增一个字段需要同时改这五处，且所有分类共用同一套字段。

目标是把字段变成数据：字段定义归属于分类，在分类管理界面里增删改，
日志表单/详情/列表按当前分类的字段定义动态渲染。

### 生产现状（2026-09-20 只读查询 NAS 得到）

| 项 | 值 |
| --- | --- |
| 分类 | `5 手套`、`6 欢欢衣服` |
| 日志 | 2 条，其中 1 条已软删；有效的 1 条属于「手套」 |
| 填过 `wire` 的日志 | 1 条，在「手套」下 |
| 图片 | 2 张 |
| 容器内 SQLite | 3.46.1（支持表达式索引与 `NULLS LAST`） |

「欢欢衣服」分类已存在且没有任何日志，因此衣服的字段由用户升级后在后台自行添加，
本设计不写死。

## 目标

1. 字段定义归属分类，可在分类管理中增删改、排序、设必填
2. 支持 6 种字段类型：`text` / `textarea` / `number` / `date` / `select` / `multiselect`
3. `select` 与 `multiselect` 的选项可自定义，支持增删改与排序
4. 现有 `wire`（线材）字段迁移为「手套」分类的自定义字段，已填值不丢
5. 列表页可按选项字段筛选、按数字/日期字段排序
6. 字段可标记为「显示在列表卡片」

## 非目标

- 字段级权限、字段历史版本
- 跨分类搜索自定义字段值（搜索框仍只搜 `description`）
- 文件/图片类型的自定义字段
- 拖拽排序（沿用现有 `sort_order` 数字输入框风格）
- `boolean`（单个是/否开关）类型。`multiselect` 已覆盖「从自定义选项中勾选多个」
  的需求；若后续确实需要独立的布尔开关，按本设计的类型扩展机制追加即可，成本很小。

## 内置字段 vs 自定义字段

经确认的划分：

- **所有分类共有的内置字段**：图片、`description`、`external_link`、`status`
- **下放为分类自定义字段**：`wire`（线材）→ 归入「手套」

理由：图片与描述是本应用的本质（图片日志），外部链接和待办/完成状态对任何分类
都适用；线材只对手套有意义。

## 数据模型

新增三张表。

```sql
-- 字段定义，属于某个分类
CREATE TABLE IF NOT EXISTS category_fields (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL,
    name         TEXT    NOT NULL,
    type         TEXT    NOT NULL
                 CHECK(type IN ('text','textarea','number','date','select','multiselect')),
    required     INTEGER NOT NULL DEFAULT 0,
    show_in_list INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

-- 下拉/多选的选项，属于某个字段
CREATE TABLE IF NOT EXISTS field_options (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id   INTEGER NOT NULL,
    label      TEXT    NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (field_id) REFERENCES category_fields(id) ON DELETE CASCADE
);

-- 日志的字段值
CREATE TABLE IF NOT EXISTS log_field_values (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id     INTEGER NOT NULL,
    field_id   INTEGER NOT NULL,
    value_text TEXT,        -- text / textarea
    value_num  REAL,        -- number
    value_date TEXT,        -- date, 'YYYY-MM-DD'
    option_id  INTEGER,     -- select / multiselect
    FOREIGN KEY (log_id)    REFERENCES logs(id)            ON DELETE CASCADE,
    FOREIGN KEY (field_id)  REFERENCES category_fields(id) ON DELETE CASCADE,
    FOREIGN KEY (option_id) REFERENCES field_options(id)   ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_lfv_uniq
    ON log_field_values(log_id, field_id, COALESCE(option_id, -1));
CREATE INDEX IF NOT EXISTS idx_lfv_opt  ON log_field_values(field_id, option_id);
CREATE INDEX IF NOT EXISTS idx_lfv_num  ON log_field_values(field_id, value_num);
CREATE INDEX IF NOT EXISTS idx_lfv_date ON log_field_values(field_id, value_date);
```

### 设计决定与理由

**代理主键而非 `(log_id, field_id)` 复合主键。**
`multiselect` 需要每个选中项一行，复合主键存不下。表达式唯一索引
`COALESCE(option_id, -1)` 同时保证：标量字段每个 `(log_id, field_id)` 只有一行
（`option_id` 为 NULL 时兜成 -1），多选字段每个选项最多一行（防重复勾选）。
SQLite 的 UNIQUE 索引视 NULL 互不相同，因此必须用 `COALESCE` 而不能直接索引
`option_id`。容器内 SQLite 3.46.1 支持表达式索引（3.9+）。

**下拉值存 `option_id` 而非文本快照。**
用户在后台把「Nike」改名成「NIKE」时，所有历史日志应当自动跟着变——这是
「选项可自定义」的应有语义。代价是删除选项需要处理引用，见下文删除策略。

**按类型分列存储而非统一 TEXT 列。**
`value_num` / `value_date` 分列才能建有意义的索引，支撑按价格、按日期排序。

**写入策略：先删后插。**
保存日志时，对每个提交的字段执行
`DELETE FROM log_field_values WHERE log_id = ? AND field_id = ?`，再插入新值
（标量一行，多选 N 行）。逻辑简单，对三类字段一致，且天然正确。

## 迁移

写在 `database.py` 的 `init_db()` 中，沿用现有 `wire` / `deleted_at` 迁移的
幂等风格，每次启动都执行、重复执行无副作用。

1. 建上述三张表与索引（`IF NOT EXISTS`）
2. 查找名为「手套」的分类。**若不存在则整个迁移到此为止**——全新部署的空库
   没有任何分类，此时不应凭空造一个「手套」出来
3. 若「手套」下不存在名为「线材」的字段，创建 `type='text'`、`sort_order=0`
   的「线材」字段；已存在则复用
4. 对**「手套」分类下**每条 `wire` 非空、且在 `log_field_values` 中尚无该字段值
   的日志，插入一行 `value_text = wire`
5. `logs.wire` 列**保留不删**，代码从此不再读写

步骤 4 限定在「手套」分类内，因为「线材」字段只归属于「手套」，
给其他分类的日志写入一个不属于其分类的 `field_id` 会破坏数据一致性。
已核查生产库：填过 `wire` 的日志只有 1 条且就在「手套」下，
不存在需要额外处置的数据。若日后在其他环境遇到这种数据，它保留在
`logs.wire` 原列中不丢失，可人工处理。

步骤 4 的「尚无该字段值」条件保证迁移可重复执行。保留 `wire` 列是因为
`DROP COLUMN` 在旧版 SQLite 上不可用，且保留一份原始数据便于回滚。

对当前生产数据的实际效果：唯一那条填了线材的手套日志，值完整搬入新表。

## API

### 字段与选项管理

```
GET    /api/categories/{cid}/fields    -> 字段定义列表，select/multiselect 内嵌 options
POST   /api/categories/{cid}/fields    -> 新建字段
PUT    /api/fields/{fid}               -> 改名/改必填/改 show_in_list/改排序
DELETE /api/fields/{fid}               -> 删除字段（级联删值）
GET    /api/fields/{fid}/usage         -> { log_count } 受影响日志数，供前端确认
POST   /api/fields/{fid}/options       -> 新建选项
PUT    /api/options/{oid}              -> 改 label / sort_order
DELETE /api/options/{oid}              -> 删除选项（级联删值）
GET    /api/options/{oid}/usage        -> { log_count }
```

字段的 `type` 创建后不可修改。改类型会让已存的值落在错误的列上，收益不抵复杂度；
需要改类型就删掉重建。这一点在前端字段编辑界面中以禁用态体现。

### 删除策略

沿用现有「分类有日志就不让删」（`categories.py:74`）的保护思路，但更友好：
删除字段或选项前，前端先调 `usage` 拿到受影响日志数，若大于 0 则弹确认框
说明「将同时清除 N 条日志中的该数据」，确认后才发 DELETE，后端级联删除。

### 日志读写

`LogOut` 增加：

```
field_values: [
  { field_id, name, type, sort_order, show_in_list,
    value,            // 标量值；select 为 option_id；multiselect 为 option_id 数组
    option_labels }   // select/multiselect 的显示文本，数组
]
```

- **创建**（`POST /api/logs`，multipart，因为同时传图片）：
  新增一个 form 字段 `field_values`，内容是 JSON 字符串，形如
  `{"12": "Nike", "15": 899, "16": "2026-03-01", "13": [34, 35]}`，
  key 为 `field_id` 的字符串形式
- **更新**（`PUT /api/logs/{id}`，JSON body）：
  `field_values` 直接是同形状的对象

后端按 `field_id` 查出字段类型，据此决定写入哪一列；`required` 为真而值为空时
返回 400。提交了不属于该分类的 `field_id` 时返回 400。

### 列表筛选与排序

```
GET /api/logs?category_id=6&fv=12:34&fv=12:35&fv=13:56&sort=15:desc
```

- `fv=<field_id>:<option_id>`，可重复
- **同一字段内多个值是 OR，不同字段之间是 AND**（标准的电商多面筛选语义）。
  对 `multiselect` 而言「包含任一选中项」即为该语义的自然结果
- `sort=<field_id>:asc|desc`，仅允许 `number` 与 `date` 类型字段；
  非法 field_id 或类型不符时忽略该参数，回落到默认排序
- 默认排序保持现状：`created_at DESC`

SQL 形状——每个被筛选的字段生成一个 `EXISTS` 子查询：

```sql
AND EXISTS (
    SELECT 1 FROM log_field_values v
    WHERE v.log_id = l.id AND v.field_id = ? AND v.option_id IN (?, ?)
)
```

排序通过 `LEFT JOIN` 到指定字段：

```sql
LEFT JOIN log_field_values s ON s.log_id = l.id AND s.field_id = ?
ORDER BY s.value_num DESC NULLS LAST
```

未填该字段的日志排在最后。

### 列表端点的批量加载

现状 `_build_log()`（`logs.py:15`）对每条日志单独查一次 images，已是 N+1；
再叠加字段值会变成每条日志两次额外查询。列表端点改为批量加载：取到当页
`log_id` 列表后，用两次 `WHERE log_id IN (...)` 分别取回全部图片与全部
`show_in_list = 1` 的字段值，在内存中组装。

列表只返回标记了 `show_in_list` 的字段值；详情端点返回该分类的全部字段值
（单条查询，无性能顾虑）。

这是改动所触及代码的顺手修复，不属于额外范围。

## 前端

### 字段管理子页（新增）

路由 `/categories/:id/fields`，从分类管理页的分类行进入。

- 字段列表，按 `sort_order` 排列，每行显示名称、类型徽章、必填/列表显示标记
- 新增字段：名称 + 类型下拉 + 必填开关 + 「显示在列表卡片」开关 + 排序数字框
- 编辑字段：类型为禁用态（见上文），其余可改
- `select` / `multiselect` 字段可展开，在其下管理选项（增删改 + 排序数字框）
- 当标记 `show_in_list` 的字段超过 3 个时，显示软提示
  「卡片空间有限，建议不超过 3 个」，不强制拦截

排序沿用现有 `Categories.vue` 的 `sort_order` 数字输入框风格，不引入拖拽库。

### 日志表单（`LogForm.vue`）

选定分类后拉取该分类字段定义并动态渲染。类型到控件的映射：

| 类型 | 控件 |
| --- | --- |
| `text` | `<input type="text">` |
| `textarea` | `<textarea rows="3">` |
| `number` | `<input type="number" inputmode="decimal">` |
| `date` | `<input type="date">`（移动端直接弹系统日历，零依赖） |
| `select` | `<select>` |
| `multiselect` | 复选框组，选项平铺 |

切换分类时清空已填的自定义字段值，避免跨分类的脏数据。必填字段用原生
`required` 属性 + 提交前校验。

现有的「线材」输入框从表单中移除——它将作为「手套」分类的自定义字段自动出现。

### 日志详情（`LogDetail.vue`）

在内置字段（描述、外部链接）之后，按 `sort_order` 渲染该日志分类的全部
自定义字段。`multiselect` 的多个值渲染成一排 pill。空值字段不显示，
与现有 `v-if="log.wire"` 的行为一致。

### 列表页（`LogList.vue`）

**筛选**：选中某个具体分类后，在现有的分类/状态 pills 下方出现该分类的
`select` 与 `multiselect` 字段筛选器；选「全部」时不显示。排序下拉列出该分类的
`number` 与 `date` 字段。

**卡片**：在描述下方、日期上方，渲染标记了 `show_in_list` 的字段，
`text-[10px]` 紧凑两列排版。卡片处于 `columns-2` 瀑布流中、宽度仅半屏，
因此：`select` / `multiselect` 渲染成小 pill，`multiselect` 超过 2 个收成 `+N`；
长文本单行截断。

```
┌──────────────┐
│  [封面图]     │
│ 衣服 ·待处理  │
│ 冬天穿的那件  │  <- description
│ 品牌  Nike    │  <- show_in_list 字段
│ 价格  ¥899    │
│ 类型  外套 +2 │  <- multiselect 收成 +N
│ 2026-09-20   │
└──────────────┘
```

## 测试

项目当前没有任何测试。本次改动涉及表结构与数据迁移，加后端接口测试：
pytest + httpx，测试依赖放在 `backend/requirements-dev.txt`，不进生产镜像。
测试用临时 SQLite 文件，通过 `DB_PATH` 环境变量注入。

覆盖点：

1. 迁移幂等——连续执行两次 `init_db()`，「线材」字段和值都不重复
2. 迁移正确——已填 `wire` 的日志迁移后能从新表读到相同的值
3. 字段 CRUD，含 `type` 创建后不可改
4. 选项重命名后，引用它的日志读出的 `option_labels` 随之变化
5. `multiselect` 写入 N 行、重复勾选被唯一索引挡下、先删后插不残留旧值
6. 筛选语义——同字段 OR、跨字段 AND
7. 排序——`NULLS LAST`，未填值的日志排最后
8. `required` 校验返回 400；提交外分类的 `field_id` 返回 400
9. 删除字段/选项级联清除对应的值；`usage` 返回的计数正确

前端不引入测试框架。

## 工作量估计

后端约 500 行，前端约 650 行（含新的字段管理子页）。

## 未决事项

无。`boolean` 类型的取舍见「非目标」。
