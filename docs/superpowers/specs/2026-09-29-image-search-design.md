# 拍照以图搜图 — 设计文档

日期：2026-09-29
状态：待实现

## 背景

用户已经录入了不少带图片的日志。现在想拍一张照片，找到库里记录过的**同一件实物**，
用来：

1. **查询已录信息**：手里拿着东西，快速看到当时录入的线材、链接、状态等
2. **找同款对比**：看库里哪些记录和它很像

「相似」指实例级匹配：换角度、换光线、换背景也要能认出同一件东西。
这排除了感知哈希（只能查重）和 CLIP 这类偏语义的模型（擅长“这是手套”，
不擅长“是不是这一只手套”）。

### 生产现状（2026-09-29 只读查询 NAS 得到）

| 项 | 值 |
| --- | --- |
| NAS CPU | Intel Celeron J3455，4 核 x86_64，无 AVX2 |
| NAS 内存 | 12GB，可用约 6GB |
| 图片 | 91 张，上传目录 262MB |
| 有效日志 | 84 条 |
| 有 ≥2 张图的日志 | 2 条 |
| 容器内 Python / SQLite | 3.12.12 / 3.46.1 |

预计规模：几百张，上限几千张。

## 目标

1. 拍照（或从相册选图）搜索，按相似度返回日志列表，点击进入详情
2. 模型在 NAS 本地运行，图片不出内网、无外部费用
3. 新上传的图片自动建立索引；历史图片上线后自动补算
4. 模型文件缺失时功能优雅降级，不影响应用其余部分

## 非目标

- 文字搜图（“红色手套”）
- 并排对比视图
- 保存查询照片
- 搜不到时一键用该照片新建日志
- 向量数据库 / 近似最近邻索引（几千张规模下暴力计算只需几毫秒）
- 混用多个模型的向量

## 方案选择

| 方案 | 结论 |
| --- | --- |
| **A. DINOv2-small + ONNX Runtime** | **采用**。自监督视觉特征，实例级检索效果好；约 90MB，384 维；CPU 可跑 |
| B. CLIP ViT-B/32 | 放弃。偏语义，同类不同件区分弱；约 350MB |
| C. OpenCV ORB/SIFT + 几何校验 | 放弃。对手套、衣服等软质可变形物体效果差，逐张比对慢 |

J3455 上 DINOv2-small 单张推理预计 1–3 秒。查询要有加载态；历史补算在后台进行。
不做 int8 量化：J3455 不支持 AVX2 / VNNI，量化收益不确定，先用 fp32，实测后再议。

## 数据模型

新增一张表，由 `database.py` 的 `init_db()` 以 `CREATE TABLE IF NOT EXISTS` 创建
（纯新增表，不需要 `user_version` 一次性迁移）：

```sql
CREATE TABLE IF NOT EXISTS image_embeddings (
    image_id  INTEGER PRIMARY KEY,
    model     TEXT    NOT NULL,   -- 模型标识，如 'dinov2-small-v1'
    vector    BLOB    NOT NULL,   -- 384 个 little-endian float32，已 L2 归一化
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
);
```

- 每张约 1.5KB，几千张共几 MB
- `model` 与当前模型标识不一致的行视为**待补算**，搜索时忽略
- 删除图片时由外键级联删除向量；日志硬删除时经 `images` 级联同样删除

## 后端

### `backend/embedding.py` —— 唯一接触模型的模块

对外接口：

```python
MODEL_ID = "dinov2-small-v1"

def available() -> bool: ...
def embed(image: PIL.Image.Image) -> numpy.ndarray: ...   # shape (384,), float32, L2 归一化
def set_embedder(fn) -> None: ...                           # 测试注入用
```

- 模型路径由环境变量 `MODEL_PATH` 指定，默认 `/app/data/models/dinov2-small.onnx`
- 文件不存在 → `available()` 为 `False`；不抛异常、不阻止应用启动
- 懒加载 onnxruntime `InferenceSession`，全局单例；`intra_op_num_threads=2`，
  避免占满 NAS 的 4 个核
- 预处理（与模型自带的 `preprocessor_config.json` 一致）：转 RGB → 短边双三次缩放到 256 →
  中心裁剪 224×224 → 按 ImageNet 均值/方差标准化 → NCHW
- 模型输入 `pixel_values`，输出 `last_hidden_state`（形状 `(1, 257, 384)`），取第 0 个 token（CLS），L2 归一化
- 推理由一把全局锁串行化

### `backend/indexer.py` —— 后台建索引

- 单个守护线程 + 队列，启动时由 `main.py` 的 startup 启动
- **新上传**：`upload_images` 在图片入库、生成缩略图之后，把 `image_id` 放进队列，
  上传接口不等待推理
- **历史补算**：线程启动后先扫描「没有向量或 `model != MODEL_ID`」的图片逐张补算，
  之后处理队列
- 使用 800px 缩略图（`uploads/thumbs/`）计算；缩略图不存在则用原图；都读不了（非图片、
  损坏）则跳过并记日志，不写向量（这类图片会一直计入 `pending`，见下）
- 每处理完一张就释放推理锁，使搜索请求最多等待一张图的推理时间
- `available()` 为 `False` 时线程不启动
- 每张独立事务写入（`INSERT OR REPLACE`），写入前确认 `images` 行仍存在，
  避免补算期间图片被删导致外键错误

`pending` 的定义：属于有效日志、但没有当前模型向量的图片数。
非图片文件会永久计入 `pending`；为避免误导，扫描时对解码失败的图片在内存中记住，
不计入 `pending`（进程重启后重新尝试一次）。

### 搜索接口 `POST /api/search/image`

新路由文件 `backend/routers/search.py`。

请求：multipart，字段 `file`（单张图片），查询参数 `limit`（默认 20，上限 50）、
`min_score`（默认 `MIN_SCORE`，供评测脚本传 -1 取回全部分数，前端不传）。

流程：

1. `available()` 为 `False`，或模型文件存在但加载失败（损坏） → 503 `"以图搜图未启用"`
2. 读入内存，用 Pillow 打开；失败 → 400 `"无法识别的图片"`；像素数超过 Pillow 的
   解压炸弹上限 → 400 `"图片尺寸过大"`。处理 EXIF 方向（`ImageOps.exif_transpose`）
3. 缩到 800px 以内（与索引用的缩略图同尺寸），`embed()` 得到查询向量；**不落盘**
4. 一次查询读出所有有效向量：
   `image_embeddings JOIN images JOIN logs WHERE logs.deleted_at IS NULL AND model = MODEL_ID`
5. 组成矩阵，与查询向量做点积得到余弦相似度
6. 按 `log_id` 聚合：取最高分及对应图片
7. 丢弃低于 `MIN_SCORE`（初值 0.3）的，按分数降序取前 `limit` 条
8. 复用 `routers/logs.py` 的 `_build_log_list()`（列表页的批量加载，`show_in_list` 字段）组装 `LogOut`，不引入逐条查询

不缓存向量矩阵：几千行读取只需毫秒级，远小于推理耗时，省掉缓存失效问题。

响应：

```json
{
  "items": [
    {
      "log": { "...": "LogOut" },
      "score": 0.87,
      "matched_image": { "...": "ImageOut" }
    }
  ],
  "indexed": 412,
  "pending": 38
}
```

`models.py` 新增 `ImageSearchHit`、`ImageSearchOut`。

### 依赖

`requirements.txt` 新增并锁定版本：`onnxruntime`、`numpy`。
（已确认 Python 3.12 / 3.14、x86_64 / macOS arm64 均有现成 wheel。）
Docker 镜像约增大 60MB。

## 前端

### 入口

- `LogList.vue` 搜索框右侧加相机图标按钮
- 按钮内含隐藏的 `<input type="file" accept="image/*">`，**不加 `capture` 属性**：
  加了 `capture` 的话 iOS / Android 会直接进相机、无法选相册。不加时手机会弹出
  「拍照 / 照片图库 / 文件」选择；桌面端为普通文件选择
- 选图后把文件交给搜索页（通过一个小的模块级 store 传递 `File` 对象），跳转 `/search/image`

### 搜索页 `views/ImageSearch.vue`，路由 `/search/image`

- 顶部：查询照片预览 + 「重新拍照」按钮
- 上传前用 `imageCompress.js` 新增的 `shrinkForSearch()` 缩到长边 1024 再上传，
  不读取压缩开关（服务端只用到 800px）
- 请求中：骨架屏 + 「正在识别…（约需几秒）」
- 结果卡片：左侧为 `matched_image` 的缩略图（不一定是日志首图）；右侧沿用列表卡片的
  信息（分类、描述、状态、`show_in_list` 字段）；右上角相似度档位标签；点击进入详情
- 相似度档位（初值，上线后按评测结果调整）：

  | 分数 | 标签 |
  | --- | --- |
  | ≥ 0.75 | 很可能是同一件 |
  | 0.5 – 0.75 | 相似 |
  | < 0.5 | 有点像 |

- 从详情页返回时结果仍在：结果和查询预览存在模块级 store，页面挂载时有结果就不重新请求；
  直接访问 `/search/image` 且没有 store 数据时，只显示拍照按钮

状态：

| 情况 | 显示 |
| --- | --- |
| 无结果 | 「没有找到相似的记录」 |
| `pending > 0` | 顶部黄色提示条「还有 N 张图片正在建立索引，结果可能不完整」 |
| 503 | 「以图搜图未启用，请联系管理员放置模型文件」 |
| 其他错误 | 错误信息 + 重试按钮 |

`api.js` 新增 `searchByImage(file, limit)`。

## 部署

- `scripts/fetch-model.sh`：下载 DINOv2-small 的 ONNX 文件到 NAS 的
  `data/models/dinov2-small.onnx`；支持 `HF_ENDPOINT` 指定镜像；下载后校验 sha256
  （脚本内写死期望值）；已存在且校验通过则跳过。首次上线前运行一次
- 模型不进 git，也不在 Docker 构建时下载（避免构建依赖外网）
- 模型缺失不影响启动与健康检查，部署不会因此回滚
- 首次上线后后台补算 91 张历史图片，预计 2–5 分钟；期间搜索可用，显示 `pending` 提示

## 测试

自动化测试在 deploy 的 pytest gate 中运行，必须快、不依赖模型文件。

- `embedding.set_embedder()` 注入假 embedder：由图片平均颜色生成确定性向量，
  使「颜色相同 = 相似」，可构造可预期的排序
- 测试中 indexer 以同步模式运行（提供 `process_pending()` 直接调用），不依赖线程时序

覆盖点：

1. 上传图片后 `process_pending()` 写入向量；删除图片后向量级联删除
2. 按日志聚合：多图日志只出现一次，分数取最高，`matched_image` 为正确的图
3. 软删日志不出现在结果中
4. 低于 `MIN_SCORE` 的不返回；`limit` 生效
5. `model` 不匹配的向量不参与搜索、计入 `pending`
6. `process_pending()` 重复运行不重复计算
7. 模型不可用：搜索返回 503；上传仍成功
8. 非图片文件：搜索返回 400；作为日志图片上传时不写向量、不计入 `pending`
9. 搜索结果的查询条数不随结果数增长（沿用 `tests/test_log_filter_sort.py` 中 `set_trace_callback` 的做法）

真实模型冒烟测试标记 `@pytest.mark.model`，默认跳过（在 `conftest.py` 中未设置
`MODEL_PATH` 或文件不存在时 skip）。验证输出形状 `(384,)`、已归一化、
同一张图的轻微裁剪版本相似度高于不同图片。

## 阈值评测

`scripts/eval-search.py`：读取一个目录的查询照片，文件名以日志 id 开头
（如 `37_a.jpg`、`37_b.jpg`），逐张通过 HTTP 调用线上搜索接口（`min_score=-1`），输出：

- 正确日志的排名分布（Top-1 / Top-3 / 未命中）
- 正确匹配与错误匹配的分数分布

生产库中只有 2 条日志有多张图，无法用库内数据自测。上线后由用户对 10–20 件已录入的
物品重新拍照作为评测集，据此确定档位阈值和 `MIN_SCORE`。

注意：合成图实测中，DINOv2 CLS 向量的余弦相似度整体偏高（无关图案也可达 0.9），
上面的档位与 `MIN_SCORE` 初值很可能不合适；在评测完成前，结果以**排序**为准，
档位标签仅供参考。

## 风险

| 风险 | 应对 |
| --- | --- |
| J3455 推理慢 | 查询有加载态；补算在后台；线程数限制为 2 |
| 同类物品（如多只相似手套）区分不出 | 评测集验证；若不够好，后续可考虑更大的 DINOv2-base 或查询时裁剪主体 |
| 模型文件下载受网络限制 | 支持 `HF_ENDPOINT` 镜像；也可手动放置文件 |
