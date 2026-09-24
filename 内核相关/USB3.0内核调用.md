![usb内核日志_1](D:\Workspace\Doc\0_个人整理\ShareDoc\supreme-octo-meme\image\usb内核日志_1.png)

现象:

在进入系统之后,如果USB3.0_A接口插升级线连接着PC,那么可以后台查出大量循环打印的usb错误信息

并且下发lsusb命令时,可能会卡住几秒到十几秒

日志记录:

```bash
[ 3729.233433] usb usb6-port1: Cannot enable. Maybe the USB cable is bad?
[ 3729.233488] usb usb6-port1: config error
```

关联内核代码位置:

```
./drivers/usb/core/hub.c
```

相关函数:

hub_port_reset

port_event

hub_event



日志直接打印位于hub_port_reset函数中

![usb内核函数_1](D:\Workspace\Doc\0_个人整理\ShareDoc\supreme-octo-meme\image\usb内核函数_1.png)

从日志打印处往回查,调用这个函数的角色是:port_event

![usb内核函数_2](D:\Workspace\Doc\0_个人整理\ShareDoc\supreme-octo-meme\image\usb内核函数_2.png)

它会在内部尝试重启端口,并且里面固定了循环重建的尝试次数和每次尝试的间隔,在超时后会进入hub_port_disable关闭这个端口,之后在走到函数末尾后退出port_event

但是由于线仍然插着,会触发新的事件重新调用hub_event,也是在这个函数里给根集线器上锁了(和lsusb同一把锁),也就是说在之前循环reset期间lsusb都会卡住等待窗口

lsusb 阻塞在等待hub_event函数内

![usb内核函数_4](D:\Workspace\Doc\0_个人整理\ShareDoc\supreme-octo-meme\image\usb内核函数_4.png)

这把锁,它会在经过hub_port_reset()中等待约4秒之后返回处理完自身状态之后释放,直到下一次事件触发



整个过程:

USB3 PHY检测到usb对端设备电气属性->xHCI硬件中断将hub_event加入工作队列->先给根集线器上锁再给端口上锁(影响lsusb的是根集线器锁)-> 进入port_event然后进入端口复位函数->  hub_port_reset重试耗尽->回到port_event并关闭这个端口->运行到函数底部返回hub_event函数,在hub_event末尾解锁根集线器->线还插着,物理接口再次触发事件回到起点



如果 lsusb 恰好在那个很短的释放窗口(hub_event解锁后到下次事件触发进入hub_event函数头部上锁之间)获得集线器锁，就会快速返回；如果没有抢到，就要再等一轮甚至多轮。



