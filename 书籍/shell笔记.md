# 文件系统部分

##### 文件系统

文件系统是操作系统用于明确存储设备（常见的是磁盘，也有基于NAND Flash的固态硬盘或分区上的文件的方法数据结构；即在存储设备上组织文件的方法。

较为常见的几个文件系统:FAT/NTFS(Windows独有)/EXT4

“根文件系统”是：

> 承载 `/` 的那个文件系统。

##### 分区

一整块磁盘切成几个独立区域。

Linux 分区是将物理硬盘划分为多个逻辑部分，通过挂载到目录来使用，与 Windows 盘符不同 。核心是根分区和交换分区，其他分区可按需划分 。‌‌

目的:可以在不同分区里创建不同文件系统.

##### 卷组

VG：Volume Group,卷组,可以理解成：

> 把多个 PV 的容量合并成一个“大资源池”。

##### 物理卷/逻辑卷

PV：Physical Volume，物理卷,可以理解成：

> LVM 能够使用的底层存储块。

PV 虽然叫“物理卷”，但它不一定等于一整块物理磁盘。可以是整个磁盘,也可以是磁盘里的一个分区.

LV：Logical Volume，逻辑卷

有了 VG ，就可以从里面切出 LV。

##### LVM

逻辑卷管理器.提供了3个功能:

```
快照:将一个已有的逻辑卷在逻辑卷在线的状态下复制到另一个设备。

条带化:跨多个物理硬盘创建一个逻辑卷

镜像:镜像是一个实时更新的逻辑卷的一份完整副本
```



# shell编程部分

#### 状态码

![Linux退出状态码](..\image\Linux退出状态码.png)

$?变量保存上一条命令退出码

默认情况下，shell脚本会以脚本中的最后一个命令的退出状态码退出.

exit命令允许你在脚本结束时指定一个退出状态码

#### 结构化命令

##### if-then

```bash
if command
then
	commands
fi
```

或

```bash
if command;then
	commands
fi
```

bashshell的if语句会运行if行定义的那个命令。如果该命令的退出状态码是0，位于then部分的命令就会被执行。

如果该命令的退出状态码是其他什么值，那then部分的命令就不会被执行，bashshell会继续执行脚本中的下一个命令。



##### if-then-else

```bash
if command;then
	commands
else
	commands
fi
```



##### 嵌套if

```bash
if command1
then
	command set 1
elif command2
then
	command set 2
elif command3
then
	command set 3
elif command4
then
	command set 4
fi
```

bash shell会依次执行if语句,只有第一个返回退出状态码0的语句中then部分会被执行.



##### test命令

​	test命令提供了在if-then语句中测试不同条件的途径。
​	如果test命令中列出的条件**成立**，test命令就会退出并返回退出状态码0，这样if-then语句就与其他编程语言中的if-then语句以类似的方式工作了。
​	如果条件**不成立**，test命令就会退出并返回退出状态码1，这样if-then语句就会失效

写为:

```bash
test condition
```
或
```bash
[condition]
```



```bash
if [ condition ]
then
commands
fi
```

test命令可以判断3类条件:
数值比较;
字符串比较;
文件比较。

![test数值比较](D:\Workspace\Doc\0_个人整理\ShareDoc\supreme-octo-meme\image\test数值比较.png)

![test字符串比较](D:\Workspace\Doc\0_个人整理\ShareDoc\supreme-octo-meme\image\test字符串比较.png)

比较符号注意需要转义为 \\>  或者 \\<

```bash
val1=baseball
val2=hockey
if [ $val1 \> $val2 ]
then
	echo "$val1 is greater than $val2"
else
	echo "$val1 is less than $val2"
fi
```

![test文件比较](D:\Workspace\Doc\0_个人整理\ShareDoc\supreme-octo-meme\image\test文件比较.png)



##### 复合条件测试

```
&&   ||
```



##### 双尖括号

```
(( expression ))
```

双尖括号命令允许将高级数学表达式放入比较中。
test命令只允许在比较中进行简单的算术操作。
双尖括号命令提供了更多的其他编程语言的程序员所熟悉的数学符号。

![双尖括号](D:\Workspace\Doc\0_个人整理\ShareDoc\supreme-octo-meme\image\双尖括号.png)



##### 双方括号

```
[[ expression ]]
```

可以用于字符串模式匹配

用正则表达式来匹配字符串值:

```bash
if [[ $USER -- r* ]]
then
	echo "Hello $USER"
else
	echo "Sorry. I do not know you"
fi
```

双方括号命令匹配了$USER环境变量来看它是否以字母r开头。

##### case命令

```bash
case variable in
patternl | pattern2) commandsl;;
pattern3) commands2;;
*) default commands;;
esac
```

检查 variable 的值

如果匹配 pattern1 或 pattern2：
    执行 commands1

如果匹配 pattern3：
    执行 commands2

如果前面都不匹配：
    执行 default_commands



)表示：

> 匹配模式写完了，后面开始执行命令。

;;表示：

> 这个分支结束。

