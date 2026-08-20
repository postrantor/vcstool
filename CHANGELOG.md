# Changelog

本文件记录相对上游 [dirk-thomas/vcstool](https://github.com/dirk-thomas/vcstool) 的可见变化。版本号沿用上游 `0.3.0`，下列条目描述本仓库 `t/dev` 上的扩展。

## Unreleased

### 新增

- `vcs import --bare`: 按裸库克隆。清单路径键若不以 `.git` 结尾，目标目录自动补上该后缀；已带 `.git` 则不再追加。不加 `--bare` 时路径完全按清单原样使用。
- 裸库二次导入: 识别已有裸库 (`HEAD` + `objects`)，跳过 `checkout` / `submodule`，避免把裸库当成普通工作树。
- `vcs import --tree PATH`: 递归导入嵌套 `.repos`。`PATH` 可以是含 `tree` 字段的清单，或在目录下查找这类清单。每个 `manifest` 在其所在目录就地导入。
- `tree.<name>.manifest`: 用相对路径指向另一份 `.repos`。条目可写 `bare`、`force`、`shallow`、`recursive`、`skip_existing`、`retry`、`workers`，这些值优先于命令行。
- `vcs import --tree PATH --manifests NAME [NAME ...]`: 与配置中的 `tree` 键取交集，只导入满足条件的子树。

### 行为

- `--tree` 与 `--input` 互斥，且字段解耦: `--tree` 只读 `tree`、忽略 `repositories`；`--input` 只读 `repositories`、忽略 `tree`。
- `--tree` 进入含 `tree` 的文件时只做索引展开；真正克隆发生在 `manifest` 指向的、仅含 `repositories` 的叶子清单上。
- 目录模式下 `--tree` 只处理带 `tree` 字段的 `.repos`，并跳过 `.git/`、`*.git/` 以及带工作树 `.git` 的目录。

### 文档

- 将 `README.rst` 改为中文 `README.md`。

## 0.3.0 - 2021-03-25

上游发布。详见 [dirk-thomas/vcstool 0.3.0](https://github.com/dirk-thomas/vcstool/releases/tag/0.3.0)。
