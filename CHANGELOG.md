# Changelog

本文件记录相对上游 [dirk-thomas/vcstool](https://github.com/dirk-thomas/vcstool) 的可见变化。本仓库在上游 `0.3.0` 之上自行递增小版本。

## Unreleased

## 0.3.1 - 2026-08-20

### 新增

- `vcs import --bare`: 按裸库克隆。清单路径键若不以 `.git` 结尾，目标目录自动补上该后缀；已带 `.git` 则不再追加。不加 `--bare` 时路径完全按清单原样使用。
- `vcs import --mirror`: 按镜像克隆 (隐含裸库，拉取全部 refs)。与 `--bare` 并列；同时指定时 `--mirror` 优先。目标目录同样自动补 `.git`。
- 裸库二次导入: 识别已有裸库 (`HEAD` + `objects`)，跳过 `checkout` / `submodule`，避免把裸库当成普通工作树。
- `vcs import --tree PATH`: 递归导入嵌套 `.repos`。`PATH` 可以是含 `tree` 字段的清单，或在目录下查找这类清单。每个 `manifest` 在其所在目录就地导入。
- `tree.<name>.manifest`: 用相对路径指向另一份 `.repos`。条目可写 `mirror`、`bare`、`force`、`shallow`、`recursive`、`skip_existing`、`retry`、`workers`，这些值优先于命令行。`mirror` 与 `bare` 同时出现时以 `mirror` 为准。
- `vcs import --tree PATH --manifests NAME [NAME ...]`: 与配置中的 `tree` 键取交集，只导入满足条件的子树。
- `vcs fetch`: 从远端更新工作树、裸库和镜像库，不修改检出。仅该命令会扫描裸库，避免 `pull` / `status` 把镜像库当工作树处理。默认会 prune，可用 `--no-prune` 关闭。

### 行为

- `--tree` 与 `--input` 互斥，且字段解耦: `--tree` 只读 `tree`、忽略 `repositories`；`--input` 只读 `repositories`、忽略 `tree`。
- `--tree` 进入含 `tree` 的文件时只做索引展开；真正克隆发生在 `manifest` 指向的、仅含 `repositories` 的叶子清单上。
- 目录模式下 `--tree` 只处理带 `tree` 字段的 `.repos`，并跳过 `.git/`、`*.git/` 以及带工作树 `.git` 的目录。

### 文档

- 将 `README.rst` 改为中文 `README.md`。

## 0.3.0 - 2021-03-25

上游发布。详见 [dirk-thomas/vcstool 0.3.0](https://github.com/dirk-thomas/vcstool/releases/tag/0.3.0)。
