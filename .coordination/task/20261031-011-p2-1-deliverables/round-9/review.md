# P2-1 · round-9 审查（α+ 整类修）

<a id="p2-1-r9-review"></a>

- 被审：[round-9 report](report.md#p2-1-r9-report)
- 审查人：Leader（DSH） · 2026-10-31
- 裁定：**通过**；进入 round-10 克隆复验

## 我亲自复核

1. `61374f7` 共 15 文件；`w6.launch.py` 只新增 `experiments_root` / `git_root` 的 `agc_root` 派生注入，8 份 YAML 各删 2 个硬编码键，C++ 默认声明原样保留。
2. 自跑 `pytest -q scripts/tests/test_root_self_location.py scripts/tests/test_p1_4_baseline_closure.py` → **36 passed**。原失败确由注释中的文本子串触发，守卫未放宽，实际参数注入仍在。
3. 自跑 `python3 tests/docs_link_check.py` → 活跃范围**断链 0**；9 条历史归档断链仍只作历史记录。
4. 误写目录的备份存在且含 **13 个文件**；原误写位置已不存在；同日 `114406-7202` 与 `114624-4681` 两个主仓合法 run 均在。备份文件清单与 MD5 已留审查输出。
5. `git diff --check` 无输出，工作树干净，未 push。

## 结论

交付路径的实验产物根与 Git 身份根均由当前 `agc_root` 派生；独立入口继续保留既有 C++ 缺省，不在本任务扩大兼容性承诺。下一步必须靠重新克隆的真实运行证明，而不是仅凭静态测试宣布闭环。