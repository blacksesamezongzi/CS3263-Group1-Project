# 前后端与算法交接

根目录 README 包含启动、环境变量和自动化验证步骤。当前页面以 160 units、真实课程和启用 weekly feasibility 的默认规则启动。

## 课程目录与来源

`backend/catalog.py` 从 `assets/data/course_details.json` 读取真实课程、prereqTree、开课学期、考试和完整 timetable。原始团队 `nusmods_modules.json` 留作 legacy 输入，不作为网页当前目录。

当前目录包含 281 门课程。分类池：ID 23、CD 17、GEA 4、GEC 35、GESS 28、GEN 27。类别之间可能重叠，不能把这些数量直接相加。ID/CD 按官方名单认定；实际 offering 按 NUSMods AY2026/27 交叉匹配。

来源：

- [SoC Common Curriculum / Appendix B、C](https://www.comp.nus.edu.sg/cug/soc-22-23/)
- [Registrar GE 批准课程清单](https://www.nus.edu.sg/registrar/academic-information-policies/undergraduate-students/general-education/list-of-courses-approved-under-the-ge-pillars)
- [CS 2026/27 学位要求](https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/)
- [NUSMods AY2026/27 API](https://api.nusmods.com/v2/2026-2027/)

执行 `.venv/bin/python scripts/refresh_catalogue.py` 可刷新。脚本实时解析官方 ID/CD 页面；GE 代码清单在脚本中按本次 Registrar 清单记录，后续官方名单变更需审阅后同步。脚本只保留实际参考学年存在的课程；并非 NUS 全目录。

所有 course_info 提供 code、title、units、semesters、categories、source_urls、nusmods_url、planner_eligible、eligibility_note。前端可以按代码、课程名、分类词搜索。研究生课程与 GEN 的年制 X/Y 课程可浏览但不进入自动池，不能用占位符代替真实课程。

## ConstraintCard

```json
{
  "id": "user_example",
  "title": "第三学期修读 CS2102",
  "description": "Year 2, semester 1",
  "strength": "hard",
  "source": "user",
  "source_urls": [],
  "rules": [{"type": "course_in_semester", "course": "CS2102", "semester": 3}]
}
```

一张卡片拥有全部嵌套规则；删除卡片就从完整活动数组中移除这些规则。后端不补回被删默认卡片。source_urls 只接受 NUS / NUSMods 的 HTTPS URL，避免把模型生成的任意链接呈现为官方要求。项目 workload 规则没有伪造官方出处。

默认 category_units 卡片替代原来的通识、ID/CD 占位课程。ID_CD 至少 12 units、两门 ID、最多一门 CD。每门课程只能分配到一个 GE / ID_CD bucket；课程总学分只计算一次。这是保守的分类分配，尚未实现全部官方 double-counting 例外。

新卡片放到对应分类前部；同一次回复含两类时保留当前 tab。动画涵盖飞入、tab 提示、新卡片高亮、删除缩小与剩余卡片移位，并尊重系统 reduced-motion。旧浏览器草稿会迁移默认 cards、移除旧占位课程引用，并保留可识别的用户偏好。

## API

| Endpoint | 作用 |
| --- | --- |
| `GET /api/config` | 版本、默认卡片、真实目录、分类池、来源、数据日期 |
| `GET /api/health` | 模型配置状态，不返回 key |
| `GET /api/models` | 后端使用 SOCLAAS key 发现模型 |
| `POST /api/preferences` | 当前消息与规则 → 校验后的新增卡片或澄清 |
| `POST /api/plans` | 完整规则 → CSP + weekly 联合验证 → 计划和班次 |
| `POST /api/timetable` | 参考 snapshot 的同一课程集合 → weekly lessons / share URL |

`/docs` 和 `/openapi.json` 为准确 schema。

```json
{
  "schema_version": 1,
  "cards": [],
  "horizon": 10,
  "start_year": 2026,
  "math_qualified": true,
  "allow_unpublished": false
}
```

学期连续编号，Y2S1=3。horizon 是变量域的硬上界；默认八学期卡片是 soft preference。空学期允许，workload minimum 只约束非空学期。

math_qualified 对应界面 H2/A-level Mathematics 资格。raw NUSMods prereqTree 不包含某些入学资格的替代分支，不能把 CS1231S、MA1521、MA1522 的桥梁课路径当成唯一入口。取消该资格后需使用真实 MA1301/MA1301X 路径。当前学生画像假定满足英语资格；输出说明这一前提。cohort 与 nOf 树节点也有显式处理，未知树节点不直接忽略。

## 算法入口与 weekly feedback

`backend/solver_adapter.py::solve_plan(request)` 是替换入口。返回 assignments（code → overall semester，0 表示未选），category_allocations、weekly_verified 等。每次请求独立进程/临时目录，工作进程移除 SOCLAAS 环境变量，避免全局 PyCSP3 状态与文件相互污染。

搜索流程：

1. 建立活动课程、学分、前置、同修、开课、考试与分类分配约束。
2. 若启用 weekly_feasibility，先加入无替代班次的固定时段冲突，并排除无可用 timetable 的 semester。
3. 求解 degree assignment，再对每个非空学期做完整 class-choice search。每种 lesson type 选择完整班次，班次内所有 meetings 一起保留；检查时段、教学周和日期。
4. 对已证明无解的课程组合缩小 conflict core，并将 no-good 回传到同一 semester parity 的所有学期。完整周排课可能有三门以上联合冲突，不能只依靠两两检查。
5. 重求 degree plan，直到各学期可行或达到限制。未知/超时不作为“已验证”。
6. 普通 Python 校验器独立复核活动 hard constraints、分类分配和 weekly 可行性。

每轮 ACE 时间上限 4 秒，最多 12 轮；迭代总时间达到约 80 秒停止，父进程 110 秒终止整个进程组。最多两个并行请求。返回 feasible 表示可行，optimal 单独表示是否证明当前目标最优；timeout 是未知状态而非无解。

严格模式遇到必选课程缺少 published/mapped 时段时返回 missing_data，不输出“完整验证”。用户主动打开条件模式时可返回 conditional，并单独列出未验证课程，weekly_verified 为 false。若删除 weekly 卡片，结果也不声称 weekly 已验证。

## CS2101 与 CS2103T

默认 corequisites 硬约束要求两门课同一个 overall semester。用户明确确认了 CS2101 与 CS2103T 的 tutorial 时段相同，本项目据此建立共享出勤映射，不能把这一用户确认的映射伪写为官方 API 提供了独立 CS2101 班次。

当前 NUSMods 将 CS2103T 的整组 Gxx 活动标为 Lecture；组内包含多个 meeting。`backend/attendance.py` 保留完整组，避免按 venue 或 duration 猜测 tutorial 子集。两门同修时只占用这组时段一次，weekly view 使用 sharedWith 显示两门课程，不制造一次重复冲突。若两门课被固定到不同学期，启用的配对规则应直接导致无解。

## SOCLAAS

[官方 API 接入文档](https://soclaas.comp.nus.edu.sg/guides/api.html)。backend-only key，模型从 `/models` 发现，chat 使用 `/v1/chat/completions`。当前消息翻译成 allow-listed JSON，提供课程目录、分类、当前规则和 schema。未知课程、类型、越界学期或不支持的 hard/soft 组合被拒绝，不执行任何模型代码，不静默漏掉请求中的一部分。

模型回复若同时包含 hard/soft 意图会拆卡；同强度的相关规则可成组。新增 card ID 由后端生成。对话不回放旧历史来重新添加已删除规则。当前聊天不修改/删除已有卡片，用户使用 Edit/× 完成这些动作。

## NUSMods

保留原生 Planner JSON 下载 + Upload。格式包括 minYear、maxYear、iblocs、ignorePrereqCheck、modules、custom。每个 module 包括 id、year、semester、index、moduleCode；实际计划不含合成占位符，custom 为空。

Weekly share URL 使用 `/timetable/sem-N/share?...` 的课程及班次编码。CS2101 在分享链接中保留课程代码，班次通过配对的 CS2103T 教学组承载；其自身 API 未提供独立 class IDs。外部 NUSMods 页面使用它当前的 academic year，而本项目规划按参考年的模式复用。

## 验证与范围

测试命令见 README。包含真实求解、同学期配对与共享时段、实际 weekly conflict 拒绝、三门课共同无解案例、分类分配、导出、DOM tab 行为、搜索与旧草稿迁移。浏览器控制服务不可用，真实渲染和动画仍需人工查看。

仍未完成完整的学位类别规则、preclusions、所有个人资格、实习/FYP 与年制课程模型。weekly 验证基于所选参考数据与用户确认的共享关系，不等于保证未发布的未来数据或完整毕业资格。

## 前置课程漏检修复：求解结果与可导出计划分开

删除卡片仍会移除对应 CSP 规则，但现在每个结果都额外执行 `academic_audit`，独立检查 prescribed foundation courses 和所有已选课程的 prerequisite 顺序。此检查不依赖客户端是否保留 `core` / `prereqs` 卡片。H2 Mathematics 仅豁免 CS1231S、MA1521、MA1522 本身的入门数学条件，不把这些课程视为已完成，也不会豁免它们对后续课程的先修作用。

`status: feasible` 仅表示活动卡片有解。若 `academic_audit.status == failed`，结果是 exploratory preview，`exportable: false`，不附带 `nusmods_planner`。前端列出缺少的基础课以及每门课未满足的前置表达式，并禁用导出；可以恢复学业规则后重新求解。

下载不再直接序列化浏览器里的 JSON。新增 `POST /api/exports/nusmods` 接收 course-to-semester assignments、horizon、start_year 和 math_qualified，由后端重新检查基础课和前置顺序后构造原生 JSON；失败返回 HTTP 409 及具体 academic_audit。客户端伪造“已通过”字段或使用旧计划不能绕过此复核。年份和学期按同一映射重建。

浏览器 draftVersion 升至 3：仅升级旧草稿时恢复漏掉的 foundation / prerequisite 默认卡片，并保留用户新增偏好；升级后主动删除仍会保留删除状态，同时显示预览/导出限制，避免暗中把规则重新加进搜索。

## Minor 约束与选课分配

新增 hard rule：`{"type":"minor_programme","programme":"mathematics"}` 或 `programme:"quantitative_finance"`。它是一条前端规则，对应后端多个课程组、unit 和重用限制；前端单独显示在 **Minors** 分类，默认 16 张卡不包含 optional minors。`GET /api/config.minors` 返回两项定义、官网/PDF 来源与当前真实课程池。Study plan 支持直接添加，也支持填入 agent prompt。

`backend/minors.py` 保存 AY2021/22-onwards 官网规则。每个 minor 的变量将课程分配到一个且仅一个组；数学为 foundation/intermediate/advanced，QF 为 introduction/mathematics/fundamentals/investment/advanced。20+ units、至少 12 distinct units、最多 8 shared units、禁止三重计入、minor 之间 entire eligible-pool 去重和明确课程 preclusion 一并进入 CSP。QF 的 MA2301 已停开，使用 Option B。`minor_allocations` 返回 programme → group → codes；`minor_audit` 用独立 Python 实现复核分组和重用，任何失败都会拒绝结果。

`assets/data/minor_course_details.json` 是独立的 AY2026/27 NUSMods supplement，保留原始主课程数据，新增 57 门课程。只有 active minor 或显式课程请求才扩展 solver pool；prerequisite 依然按实际 AND/OR 树处理，不把 preclusion 当作 prerequisite 替代。H2 Mathematics qualification 对仅以 MA1301/MA1301X 为入门条件的课程生效，不豁免后续先修课程本身。

导出时前端增加 `minors`、`minor_allocations`、`category_allocations`，服务端再次复核；无 minor 的旧请求兼容。SoCLaaS plain chat 的 `minor_prompt_cards` 与上面的 definitions 共用数据，单独归到 Minors；不会自动随 Add all defaults 加入。UI 手动插入的 prompt 才会发送给纯模型。

这些规则假设 CS primary major、NUS-earned credits，不执行 EduRec declaration、个人 exemption 或完整 CourseReg programme/grade eligibility。支持学期 5 之前的申报提醒，不声称自动完成申报或完整毕业认证。
