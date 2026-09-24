# 干线绿波发车窗口 API

基于 **Python 3.11 + FastAPI** 的干线（arterial）绿波发车窗口计算服务。

给定干线上至多 8 个路口各自的信号周期、相位偏移、周期内绿灯半开区间（允许跨周期零点）
以及从起点到该路口的行驶秒数（可选波动上限 `travel_max`：实际行驶时间可取
`[travel, travel_max]` 内任意实数秒），并给定一个不超过 3600 秒（一小时）的整数秒
**半开**发车范围，服务返回在该范围内出发、对行驶时间区间内的**任意**取值都能在抵达
**每个**路口时遇到绿灯的**全部极大半开发车区间**，按起点升序排列；不存在任何可行窗口时
返回空数组 `[]`。省略 `travel_max`（或令其等于 `travel`）时退化为固定行驶时间，
语义与旧版完全一致。

## 目录结构

```
.
├── app/
│   ├── __init__.py
│   ├── greenwave.py      # 纯算法：周期展开 + 区间求交，无逐秒试探
│   ├── schemas.py        # Pydantic 请求/响应模型与输入校验
│   └── main.py           # FastAPI 入口与路由
├── tests/                # pytest 测试（含 600 组随机用例的逐秒对照）
├── conftest.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 一条命令安装依赖并启动（推荐 Docker）

需要本机已安装 Docker 与 Docker Compose 插件（Docker Desktop 自带）：

```bash
docker compose up --build -d
```

该命令会完成镜像构建、依赖安装并在后台启动服务。查看日志：

```bash
docker compose logs -f
```

停止：

```bash
docker compose down
```

> 旧版独立命令 `docker-compose up --build -d` 同样可用。

### 无 Docker 时的本地启动

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API 地址与端口

| 用途 | 地址 |
| --- | --- |
| 健康检查 | `GET http://localhost:8000/health` |
| 绿波窗口计算 | `POST http://localhost:8000/api/green-wave/windows` |
| 交互式文档（Swagger UI） | `http://localhost:8000/docs` |
| OpenAPI 描述 | `http://localhost:8000/openapi.json` |

## 必要配置

所有配置均有默认值，不改任何文件即可启动：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8000` | **宿主机**暴露端口（容器内固定监听 8000）。8000 被占用时：`cp .env.example .env` 后改成如 `APP_PORT=8080`，再重新 `docker compose up -d` |
| `LOG_LEVEL` | `info` | uvicorn 日志级别（`critical`/`error`/`warning`/`info`/`debug`） |

## 时间与相位语义（重要约定）

所有时间量均为**整数秒**。对路口 *i*：

- `cycle`：信号周期 `C`（秒），`1 <= C <= 86400`；
- `offset`：相位偏移 `o`，`0 <= o < C`。绝对时刻 `t` 在该路口的本地相位为
  `(t + o) mod C`；
- `green_start` / `green_end`：周期内绿灯**半开区间**端点，均满足 `0 <= g < C`：
  - `green_start < green_end`：绿灯为 `[green_start, green_end)`；
  - `green_start > green_end`：绿灯**跨周期零点**，展开为
    `[green_start, C) ∪ [0, green_end)`；
  - `green_start == green_end`：整周期常绿 `[0, C)`；
- `travel`：从起点到该路口的行驶秒数下限 `T >= 0`；
- `travel_max`：可选的行驶秒数上限 `T_max`，满足 `T <= T_max <= 86400`；
  省略时默认 `T_max = T`。实际行驶时间可取**闭区间** `[T, T_max]` 内的任意
  实数秒（不只是整数秒）。设波动量 `slack = T_max - T`，出发时刻 `t` 可行当且仅当
  抵达相位弧 `[(t + T + o) mod C, (t + T_max + o) mod C]` **整体**落入绿灯：
  等价于把绿灯弧的入口端收缩 `slack` 秒。
  - 普通绿灯 `[a, b)`：`slack < b - a` 时收缩为 `[a, b - slack)`，否则无窗口；
  - **跨周期零点**绿灯：先视为覆盖零点的连续弧 `[green_start, C + green_end)`，
    收缩后再映射回 `[0, C)`（可能仍跨零点、也可能缩成一段或缩为空）；
  - `green_start == green_end` 的**整周期常绿不受任何波动影响**。
- 发车范围为半开区间 `[depart_from, depart_to)`，长度 `1 .. 3600` 秒。

固定行驶时间（`slack = 0`）时收缩退化为恒等：出发时刻 `t` 对该路口可行，当且仅当
`(t + T + o) mod C` 落在绿灯相位集合中。输出窗口同为半开区间 `[start, end)`：
`start` 时刻可行、`end` 时刻不可行（此刻在最坏行程取值下到达为红灯）。

## 请求与响应

请求体：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `depart_from` | int | `>= 0`，发车范围起点（含） |
| `depart_to` | int | `> depart_from`，且 `depart_to - depart_from <= 3600` |
| `intersections` | array | 1..8 个路口 |
| `intersections[].name` | string? | 可选名称，仅用于辨识 |
| `intersections[].cycle` | int | `1..86400` |
| `intersections[].offset` | int | `0 <= offset < cycle` |
| `intersections[].green_start` | int | `0 <= green_start < cycle` |
| `intersections[].green_end` | int | `0 <= green_end < cycle` |
| `intersections[].travel` | int | `0 <= travel <= 86400`，行驶秒数下限 |
| `intersections[].travel_max` | int? | 可选，`travel <= travel_max <= 86400`；省略时默认等于 `travel`（无波动） |

成功响应为窗口数组（可能为空）：

```json
[ { "start": 0, "end": 30 }, { "start": 60, "end": 90 } ]
```

### 示例 1：两路口绿波带

两个周期 60 秒的路口，绿灯均为本地相位 `[0,30)`；路口 1 在起点（行驶 0 秒），
路口 2 行驶 30 秒，且下游相位偏移 `offset=30` 恰好补偿行程时间（即下游信号
比上游晚 30 秒启绿）。发车范围 `[0,300)`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 300,
    "intersections": [
      {"cycle": 60, "offset": 0,  "green_start": 0,  "green_end": 30, "travel": 0},
      {"cycle": 60, "offset": 30, "green_start": 0,  "green_end": 30, "travel": 30}
    ]
  }'
```

响应（每周期内前 30 秒出发可全程遇绿）：

```json
[{"start": 0, "end": 30}, {"start": 60, "end": 90},
 {"start": 120, "end": 150}, {"start": 180, "end": 210},
 {"start": 240, "end": 270}]
```

### 示例 2：绿灯跨零点

绿灯相位为 `[50,60) ∪ [0,10)`，行驶 5 秒，发车范围 `[0,125)`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 125,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 50, "green_end": 10, "travel": 5}
    ]
  }'
```

响应（跨零点的本地绿灯被展开后与发车范围求交）：

```json
[{"start": 0, "end": 5}, {"start": 45, "end": 65}, {"start": 105, "end": 125}]
```

### 示例 3：无解

两个路口的可行时段互不相交时返回空数组：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 60,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 10, "travel": 0},
      {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 30, "travel": 0}
    ]
  }'
# []
```

### 示例 4：行驶时间波动（travel_max）

两个周期 60 秒的路口，发车范围 `[0,300)`：

- 路口 1：绿灯本地相位 `[0,30)`，行驶时间可能是 `[0,5]` 秒内任意实数；
  绿灯入口端收缩 5 秒，只剩 `[0,25)` 能保证全程遇绿；
- 路口 2：整周期**常绿**（`green_start == green_end`），行驶时间 `[30,40]` 秒、
  相位偏移 30 秒；常绿不受波动影响，该路口不额外收缩窗口。

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 300,
    "intersections": [
      {"cycle": 60, "offset": 0,  "green_start": 0, "green_end": 30,
       "travel": 0,  "travel_max": 5},
      {"cycle": 60, "offset": 30, "green_start": 0, "green_end": 0,
       "travel": 30, "travel_max": 40}
    ]
  }'
```

响应（每周期只剩 25 秒宽的稳健窗口；末段受发车范围上界 300 限制）：

```json
[{"start": 0, "end": 25}, {"start": 60, "end": 85},
 {"start": 120, "end": 145}, {"start": 180, "end": 205},
 {"start": 240, "end": 265}]
```

> 说明：路口 1 的绿灯为 `[0,30)`，波动 5 秒后收缩为 `[0,25)`；路口 2 为
> 整周期常绿，无论实际行驶 30 秒还是 40 秒（或之间任意值）到达均为绿灯。
> 若绿灯**跨周期零点**，服务会先把两段绿灯视为覆盖零点的一条连续弧再收缩，
> 避免零点附近的可行时刻被误删；波动量大于等于绿灯弧长度（普通绿灯恰等长时，
> 半开区间内放不下长度等于弧长的闭抵达弧）时该路口贡献空数组，整体结果为 `[]`。

## 输入校验与错误

无效周期、相位偏移、绿灯端点、行驶时间、`travel_max < travel` 或
`travel_max > 86400`，或路口数、发车范围长度越界时返回
`422 Unprocessable Entity`，响应体含中文原因，例如：

```json
{ "detail": ["offset 必须满足 0 <= offset < cycle（路口 中山路）"] }
```

字段类型错误、缺失字段也由 Pydantic 统一返回 422。

## 算法说明（区间运算，不逐秒试探）

1. **周期内展开与波动收缩**：每个路口的绿灯半开区间展开为 `[0,C)` 内至多两段
   （`g_start > g_end` 时为 `[g_start,C)` 与 `[0,g_end)`；相等时为整周期）。
   若提供 `travel_max`，令 `slack = travel_max - travel`：在覆盖零点的连续
   绿灯弧上把入口端收缩 `slack` 秒（跨零点弧先在 `[g_start, C + g_end)` 上
   收缩再映射回 `[0,C)`；整周期常绿保持不变；弧长不足则该路口无可行段）。
2. **映射到出发时间轴**：行驶时间下限与相位偏移合并为 `shift = (T + o) mod C`，
   收缩后的本地绿灯 `[a,b)` 对应出发时间轴上周期重复的
   `[kC + a - shift, kC + b - shift)`。只枚举与发车范围有非空交的周期 `k`
   （由整除直接算出 `k_min / k_max`），裁剪进 `[depart_from, depart_to)`，
   并合并重叠或端点相接（`[a,b)` 与 `[b,c)`）的区间。
3. **多路口求交**：各路口的有序区间列表用双指针两两求交，得到交集的全部连通段；
   交集为空立即返回。最终结果天然是全部**极大**区间，按起点升序输出。

复杂度约为 `O(路口数 × (范围长度 / 最小周期))` 次区间运算；对一小时范围、
周期最小 1 秒的极端情形，每路口也仅约 3600 个区间。

## 运行测试

```bash
pip install pytest
pytest -q
```

测试包含边界场景（跨零点、偏移、范围边界、半开端点不含、无解、行驶时间波动
收缩）以及共 600 组随机参数下与逐秒判定参考实现（固定行程 + 波动抵达弧）的
逐项对照。
