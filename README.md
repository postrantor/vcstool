# vcstool 是什么?

vcstool 是一套版本控制 (VCS) 工具，用来同时操作多个仓库。

注意: 不要和 [vcstools](https://github.com/vcstools/vcstools/) (末尾多一个 `s`) 混淆。后者提供的是一套操作各类 VCS 的 Python API。两者主要差别如下:

- `vcstool` 除了文件系统里已有的仓库工作副本外，不维护其它状态。
- `vcstool export` 用仓库的相对路径作为 YAML 键，从设计上避免路径冲突。
- 算上命令行工具，`vcstool` 的代码量明显少于 `vcstools`。

## Python 2.7 / <= 3.4

仍支持 Python 2.7 以及 Python <= 3.4 的最后一个版本是 0.2.x，见 [0.2.x 分支](https://github.com/dirk-thomas/vcstool/tree/0.2.x)。

# 工作原理

vcstool 从给定目录开始，递归查找受支持的仓库，再对每个仓库调用原生 VCS 客户端执行请求的命令 (例如 _diff_)。

# 支持哪些 VCS?

vcstool 支持 [Git](http://git-scm.com)、[Mercurial](https://www.mercurial-scm.org/)、[Subversion](http://subversion.apache.org)、[Bazaar](http://bazaar.canonical.com/en/)。

# 怎么用?

`vcs` 的用法接近 `git`、`hg` 等客户端。`help` 会列出可用命令及简要说明:

```bash
vcs help
```

默认在当前目录下查找仓库。也可以传入一个或多个路径:

```bash
vcs status /path/to/several/repos /path/to/other/repos /path/to/single/repo
```

# 导出与导入仓库集合

vcstool 可以导出、导入一组仓库的版本信息，便于复现同一套检出。编码格式是简单的 [YAML](http://www.yaml.org/)。

根键是 `repositories`，其下每个本地仓库用相对路径作为键。每个条目包含 `type`、`url`、`version`。省略 `version` 时使用默认分支。

下面是两个仓库的例子 ([vcstool](https://github.com/dirk-thomas/vcstool) 用 Git 克隆，[rosinstall](http://github.com/vcstools/rosinstall) 用 Subversion 检出):

```yaml
repositories:
  vcstool:
    type: git
    url: git@github.com:dirk-thomas/vcstool.git
    version: master
  old_tools/rosinstall:
    type: svn
    url: https://github.com/vcstools/rosinstall/trunk
    version: 748
```

## 导出仓库集合

`vcs export` 以 [YAML](http://www.yaml.org/) 输出每个仓库的路径、类型、URL 和版本。通常重定向到文件:

```bash
vcs export > my.repos
```

若当前停在某分支尖端，导出会跟随该分支。之后再 import 时，如果远端分支已前进，可能拿到更新的提交。若本地分支相对远端已有超前提交，import 也不一定能回到完全相同的状态。

要导出精确修订，使用 `--exact`。对 Git 和 Mercurial 来说，具体 hash 并不绑定某个分支或远端，工具会检查当前 hash 是否存在于任一远端。若出现在多个远端，优先考虑 `origin` 和 `upstream`，其余按字母序。

## 导入仓库集合

`vcs import` 从 `stdin` 读取 YAML 并克隆其中的仓库。通常把先前导出的文件重定向进去:

```bash
vcs import < my.repos
```

`import` 也支持 [rosinstall 文件格式](http://www.ros.org/doc/independent/api/rosinstall/html/rosinstall_file_format.html)。除了本地文件路径，还可以传入 URL。

`--mirror` 按镜像克隆 (包含全部引用，隐含裸库)。`--bare` 按普通裸库克隆。两者都会在路径键未以 `.git` 结尾时自动补上该后缀。同时指定时 `--mirror` 优先。都不加时，目标目录完全按清单中的路径原样使用。

`--tree` 与 `--input` 相互解耦:

- `--tree` 只解析 `tree` 字段，忽略 `repositories`
- `--input` 只解析 `repositories` 字段，忽略 `tree`

`tree` 的每个条目用 `manifest` 指向另一份相对路径下的 `.repos` 文件，其余子字段对应 `vcs import` 的同名参数。条目里的值优先于命令行。`--manifests NAME [NAME ...]` 与配置中的 `tree` 键取交集。完整 schema 见仓库管理根目录的 `repos` 示例。

```bash
vcs import --tree ~/.repositories/repos
vcs import --tree ~/.repositories/repos --manifests ai2rob
vcs import --input ./robocore-iii.repos --mirror --force
```

```yaml
tree:
  <name>:                          # 供 --manifests 取交集
    manifest: <relpath>            # 必填，相对本文件
    mirror: true                   # --mirror (优先于 bare)
    bare: false                    # --bare
    force: true                    # --force
    shallow: false                 # --shallow
    recursive: false               # --recursive
    skip_existing: false           # --skip-existing
    retry: 2                       # --retry N
    workers: 6                     # -w / --workers N
    debug: false                   # --debug
    repos: false                   # --repos
```

仅 `import` 支持伪客户端 `tar` 和 `zip`: 从 URL 拉取归档并解压。这两种类型的 `version` 可选；若指定，只解压归档中该子目录下的内容。

## 校验仓库清单

`vcs validate` 从 `stdin` 读取 YAML，校验内容和格式。可以把导出文件或手写清单重定向进去:

```bash
vcs validate < my.repos
```

`validate` 同样支持 [rosinstall 文件格式](http://www.ros.org/doc/independent/api/rosinstall/html/rosinstall_file_format.html)。

# 进阶功能

## 显示自最近 tag 以来的日志

`vcs log` 支持 `--limit-untagged`，输出最近一个 tag 之后的提交。

## 并行与 stdin

默认按 CPU 核数并行处理多个仓库。若底层命令需要从 `stdin` 读入，并行会冲突。要分别向每个命令提供输入，必须串行执行。例如需要交互输入凭据时:

```bash
--workers 1
```

若仓库使用 `git@` SSH URL 且主机尚未加入 known_hosts，`vcs import` 会自动退回单 worker。

## 运行任意命令

`vcs custom` 可以把任意参数交给底层 VCS。也可以按类型限制仓库集合:

```bash
vcs custom --git --args log --oneline -n 10
```

若命令要同时作用在多种仓库上，请只传对各类型都有效的通用参数。

# 如何安装?

Debian 系平台推荐安装 `python3-vcstool`。Ubuntu 上用 `apt-get`。

如果在用 [ROS](https://www.ros.org/)，可以直接从 ROS 源安装:

```bash
sudo sh -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" > /etc/apt/sources.list.d/ros-latest.list'
sudo apt install curl # 若尚未安装 curl
curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo apt-key add -
sudo apt-get update
sudo apt-get install python3-vcstool
```

如果不用 ROS，或希望尽快拿到最新发布，可以从 [packagecloud.io](https://packagecloud.io/dirk-thomas/vcstool) 安装:

```bash
curl -s https://packagecloud.io/install/repositories/dirk-thomas/vcstool/script.deb.sh | sudo bash
sudo apt-get update
sudo apt-get install python3-vcstool
```

其它系统使用 [PyPI](http://pypi.python.org) 包装:

```bash
sudo pip install vcstool
```

本仓库的扩展 (例如 `--tree`、`--bare` 后缀) 需要从源码安装:

```bash
# 在本仓库顶层
pip3 install --user -e .
```

## 配置自动补全

bash、tcsh、zsh、fish 都可以为各 VCS 命令启用补全。需要 source 对应的补全脚本。

bash，写入 `~/.bashrc`:

```bash
source /usr/share/vcstool-completion/vcs.bash
```

tcsh，写入 `~/.cshrc`:

```bash
source /usr/share/vcstool-completion/vcs.tcsh
```

zsh，写入 `~/.zshrc`:

```bash
source /usr/share/vcstool-completion/vcs.zsh
```

fish，写入 `~/.config/fish/config.fish`:

```bash
source /usr/share/vcstool-completion/vcs.fish
```

# 如何参与?

## 如何报告问题?

请先确认已使用最新版本。确认问题尚未被报告后，可在 [GitHub](https://github.com/dirk-thomas/vcstool/issues) 提单。

请尽量附上 vcstool、操作系统、Python 的版本号，以及能复现问题的命令示例。

## 如何试用最新改动?

source `setup.sh` 会把 `src` 加到 `PYTHONPATH` 前面，把 `scripts` 加到 `PATH` 前面。然后可以用 `vcs-COMMAND` (注意 `vcs` 和命令之间是连字符，不是空格)。

也可以用 pip 的 `-e/--editable`:

```bash
# 在本仓库顶层
pip3 install --user -e .
```
