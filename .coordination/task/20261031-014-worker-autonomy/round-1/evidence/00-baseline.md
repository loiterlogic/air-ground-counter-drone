<a id="top"></a>
# 00 · 接单基线（F3）

- 时间：2026-10-31T14:49:26+08:00
- 会话 ID：51e1c7d4-22e4-4152-845a-ce791e04256c
- 父 Leader 会话：session-67852665-5105-4e66-836a-bbf8ae36b6f0
- HEAD：cedbc0e6c1e0e23aaf5b0effbf42ed9bf405def6（main）
- 计划基线：cedbc0e6c1e0e23aaf5b0effbf42ed9bf405def6

## 白名单文件 sha256（改前）
```
ef5b79984e4d03e978f320c90ff27b4533b40c8b29418435ca9fc3d89d3aa225  .coordination/README.md
cbbf3d5d829901dec1882c62e89d9cdab77be23c08a32783cc9eb9c0fe1a6173  .coordination/roles/leader.md
9690ce6e6b20f321444a27490beeb934e26b3bee068b33bbee423c1507567437  .coordination/roles/worker.md
```

## 行数（改前）
```
  271 .coordination/README.md
   63 .coordination/roles/leader.md
   68 .coordination/roles/worker.md
  402 total
```

## 工作区已有改动（预期，四单同期 + Leader 归档）
```
 M .coordination/CURRENT.md
 M .coordination/README.md
 M .coordination/roles/leader.md
 M AGENTS.md
 M MAP_DESIGN_PLAYBOOK.md
 M README.md
 M docs/adr/0103-vision-perception-decision-path.md
 M docs/adr/0104-batch-authorization-and-stall-circuit-breaker.md
 M docs/adr/0105-retire-trae-and-relocate-specs-skills.md
 M docs/archive/README.md
RM docs/plan/README.md -> docs/archive/completion-20261031/README.md
RM "docs/plan/p0-1-\351\241\271\347\233\256\345\256\214\346\210\220\345\256\232\344\271\211.md" -> "docs/archive/completion-20261031/p0-1-\351\241\271\347\233\256\345\256\214\346\210\220\345\256\232\344\271\211.md"
RM "docs/plan/p0-2-\346\232\202\345\201\234\350\277\201\347\247\273\344\270\216\345\237\272\347\272\277\345\233\272\345\256\232.md" -> "docs/archive/completion-20261031/p0-2-\346\232\202\345\201\234\350\277\201\347\247\273\344\270\216\345\237\272\347\272\277\345\233\272\345\256\232.md"
RM "docs/plan/p0-3-\346\226\207\346\241\243\347\230\246\350\272\253\344\270\216\345\205\245\345\217\243\351\207\215\346\236\204.md" -> "docs/archive/completion-20261031/p0-3-\346\226\207\346\241\243\347\230\246\350\272\253\344\270\216\345\205\245\345\217\243\351\207\215\346\236\204.md"
RM "docs/plan/p0-4-\350\204\232\346\234\254\347\263\273\347\273\237\347\230\246\350\272\253.md" -> "docs/archive/completion-20261031/p0-4-\350\204\232\346\234\254\347\263\273\347\273\237\347\230\246\350\272\253.md"
RM "docs/plan/p0-5-\345\215\217\344\275\234\346\210\220\346\234\254\346\262\273\347\220\206.md" -> "docs/archive/completion-20261031/p0-5-\345\215\217\344\275\234\346\210\220\346\234\254\346\262\273\347\220\206.md"
RM "docs/plan/p1-1-\345\234\260\345\233\276\344\270\216\345\234\272\346\231\257\350\265\204\344\272\247.md" -> "docs/archive/completion-20261031/p1-1-\345\234\260\345\233\276\344\270\216\345\234\272\346\231\257\350\265\204\344\272\247.md"
RM "docs/plan/p1-2-\344\270\200\351\224\256\346\274\224\347\244\272\345\205\245\345\217\243.md" -> "docs/archive/completion-20261031/p1-2-\344\270\200\351\224\256\346\274\224\347\244\272\345\205\245\345\217\243.md"
RM "docs/plan/p1-3-\344\273\273\345\212\241\345\217\257\350\247\202\346\265\213\344\270\216\346\274\224\347\244\272\345\221\210\347\216\260.md" -> "docs/archive/completion-20261031/p1-3-\344\273\273\345\212\241\345\217\257\350\247\202\346\265\213\344\270\216\346\274\224\347\244\272\345\221\210\347\216\260.md"
RM "docs/plan/p1-4-\350\247\206\350\247\211\347\256\227\346\263\225\346\216\245\345\205\245.md" -> "docs/archive/completion-20261031/p1-4-\350\247\206\350\247\211\347\256\227\346\263\225\346\216\245\345\205\245.md"
RM "docs/plan/p2-1-\351\241\271\347\233\256\344\272\244\344\273\230\347\211\251.md" -> "docs/archive/completion-20261031/p2-1-\351\241\271\347\233\256\344\272\244\344\273\230\347\211\251.md"
 M docs/archive/ros1-baseline.md
 M docs/faq.md
 M docs/plan/PAUSED.md
?? .coordination/task/
?? docs/plan/README.md
?? docs/plan/f1-spawn-layout.md
?? docs/plan/f2-architecture-diagram.md
?? docs/plan/f3-worker-autonomy.md
?? docs/plan/f4-map-design-skill.md
```

## 本单相关锚点（改前）
```
.coordination/README.md:1:<a id="protocol"></a>
.coordination/README.md:8:<a id="roles"></a>
.coordination/README.md:29:<a id="files"></a>
.coordination/README.md:49:<a id="batch"></a>
.coordination/README.md:126:<a id="workflow"></a>
.coordination/README.md:148:<a id="run-tiers"></a>
.coordination/README.md:170:<a id="offline-budget"></a>
.coordination/README.md:187:<a id="self-correction"></a>
.coordination/README.md:192:<a id="post-archive-sidecar"></a>
.coordination/README.md:207:<a id="executor-autonomy"></a>
.coordination/README.md:226:<a id="templates"></a>
.coordination/README.md:236:<a id="auto-wake"></a>
.coordination/README.md:260:<a id="wake"></a>
.coordination/roles/leader.md:1:<a id="role"></a>
.coordination/roles/leader.md:8:<a id="duty"></a>
.coordination/roles/leader.md:16:<a id="spawn"></a>
.coordination/roles/leader.md:37:<a id="waiting"></a>
.coordination/roles/leader.md:49:<a id="review"></a>
.coordination/roles/worker.md:1:<a id="role"></a>
.coordination/roles/worker.md:10:<a id="startup"></a>
.coordination/roles/worker.md:31:<a id="batch-autonomy"></a>
```

## 收尾指纹（改后，供 Leader 抽样核对）

```
改后时间：2026-10-31T15:05+08:00
4ca9170914b9654bf958c83ad5e27d45a221a9ace72efa34e4c7da276afbcfc3  .coordination/README.md
20d7026052739a49bf26a0e269c5aec428641657bc29e6a310f9d111857dd2a5  .coordination/roles/leader.md
4822293326b132d545129a006221a59e6b9e29f8c9abae40b46f1cfd91ab1b10  .coordination/roles/worker.md
```

| 文件 | 改前行数 | 改后行数 | 改前 sha256（前 16） | 改后 sha256（前 16） |
|---|---|---|---|---|
| `.coordination/README.md` | 271 | 370 | `ef5b79984e4d03e9` | `4ca9170914b9654b` |
| `.coordination/roles/leader.md` | 63 | 73 | `cbbf3d5d829901de` | `20d7026052739a49` |
| `.coordination/roles/worker.md` | 68 | 97 | `9690ce6e6b20f321` | `4822293326b132d5` |

- `git diff --numstat`（三文件，含 Leader 接单前的链接迁移编辑）：README `+153/−54`、leader `+18/−8`、worker `+44/−15`。
- **CURRENT.md 的 mtime 仍为 14:43:54**（早于我接单 14:49），证明本单未改 CURRENT。
- 全库 `python3 tests/docs_link_check.py`：改前 exit 0 → 改后 exit 0，活跃断链 0。
