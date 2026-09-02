# NeoVim 快捷键（LazyVim）

## 启动

| 命令 | 说明 |
|---|---|
| `nvim` | 启动首页 |
| `nvim .` | 在当前项目目录启动 |
| `nvim 文件名.c` | 直接打开文件 |

## 按键记法

| 写法 | 含义 |
|---|---|
| `<Space>` | Leader 主快捷键 |
| `<C-s>` | Ctrl+s |
| `<S-h>` | Shift+h |
| `<A-j>` | Alt+j |

## 常用

| 快捷键 | 功能 |
|---|---|
| `<Space>`（稍等） | 显示可用快捷键菜单 |
| `<Space>sk` | 搜索所有快捷键 |
| `<C-s>` | 保存文件 |
| `<Esc>` | 退出当前模式并清除搜索高亮 |
| `<Space>qq` | 退出全部 Neovim 窗口 |
| `<Space>l` | 打开 Lazy 插件管理界面 |
| `<Space>fn` | 新建文件 |

## 文件与搜索

| 快捷键 | 功能 |
|---|---|
| `<Space><Space>` | 搜索项目文件 |
| `<Space>/` | 搜索项目中的文字 |
| `<Space>,` | 切换已打开的文件 |
| `<Space>e` | 打开项目文件树 |
| `<Space>E` | 打开当前目录文件树 |
| `<Space>ff` | 搜索项目文件 |
| `<Space>fF` | 搜索当前目录文件 |
| `<Space>fr` | 最近打开的文件 |
| `<Space>fc` | 搜索 LazyVim 配置文件 |
| `<Space>sh` | 搜索帮助文档 |
| `<Space>sd` | 搜索诊断信息 |

## Buffer 与窗口

| 快捷键 | 功能 |
|---|---|
| `<S-h>` / `<S-l>` | 上一个/下一个 Buffer |
| `<Space>bd` | 关闭当前 Buffer |
| `<Space>bo` | 关闭其他 Buffer |
| `<Space>bb` | 切换到上一个 Buffer |
| `<C-h/j/k/l>` | 在窗口之间移动 |
| `<Space>-` | 上下分屏 |
| `<Space>\|` | 左右分屏 |
| `<C-方向键>` | 调整窗口大小 |
| `<Space>wm` | 最大化/还原当前窗口 |

## 终端

| 快捷键 | 功能 |
|---|---|
| `<C-/>` | 打开/关闭项目终端 |
| `<Space>ft` | 打开项目根目录终端 |
| `<Space>fT` | 打开当前目录终端 |

## 编程 / LSP

> 需要对应语言的 LSP 正常启动。

| 快捷键 | 功能 |
|---|---|
| `gd` | 跳转到定义 |
| `gD` | 跳转到声明 |
| `gr` | 查找引用 |
| `gI` | 跳转到实现 |
| `gy` | 跳转到类型定义 |
| `K` | 显示类型/函数说明 |
| `gK` | 显示函数签名 |
| `<Space>ca` | Code Action |
| `<Space>cr` | 重命名符号 |
| `<Space>cf` | 格式化代码 |
| `<Space>cd` | 显示当前行诊断 |
| `[d` / `]d` | 上一个/下一个诊断 |
| `<Space>xx` | 打开诊断列表 |
| `<Space>cs` | 显示代码符号 |

> 注：系统有 `/usr/bin/clangd`，但 LazyVim 的 clangd 扩展未启用，C/C++ 的 LSP 功能暂不生效。可在 `:LazyExtras` 启用 `lang.clangd`，无需升级系统。

## 自动补全

| 快捷键 | 功能 |
|---|---|
| `<C-Space>` | 手动打开补全 |
| `<C-n>` / `<C-p>` | 下一项/上一项 |
| `↑` / `↓` | 选择补全项目 |
| `<Enter>` | 接受补全 |
| `<C-e>` | 关闭补全窗口 |
| `<Tab>` / `<S-Tab>` | 前进/后退代码片段位置 |

## Git

| 快捷键 | 功能 |
|---|---|
| `[h` / `]h` | 上一个/下一个代码改动 |
| `<Space>gs` | Git 状态 |
| `<Space>gd` | Git Diff |
| `<Space>gb` | 当前行 Git Blame |
| `<Space>gl` | Git 提交记录 |