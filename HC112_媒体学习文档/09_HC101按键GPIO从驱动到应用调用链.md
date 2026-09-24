# HC101 按键 GPIO 从驱动到应用调用链

> 工程：`Z:\HC101_A_SPC020`  
> 产品配置：`CONFIG_HC101_A_GB_X10`、`gc4653_ahd_128M_X10`  
> 平台：Hi3516CV610 / Linux  
> 说明：本文保存于 `HC112_媒体学习文档` 目录，但分析对象和代码来源均为 **HC101_A_SPC020**。

## 1. 总体结论

HC101 的实体按键没有使用 Linux input 子系统的 `/dev/input/eventX`，也不是 GPIO 中断直接通知应用。当前实现采用以下机制：

1. GPIO 内核驱动注册字符设备 `/dev/ot_gpio`；
2. 板级初始化配置按键管脚复用，并向按键 HAL 注册 GPIO0_0、GPIO0_7；
3. 用户态按键 HAL 打开 `/dev/ot_gpio`；
4. KEYMNG 线程每 200 ms 调用一次按键 HAL；
5. 按键 HAL 通过 `ioctl(GPIO_SET_DIR)` 和 `ioctl(GPIO_READ_BIT)` 读取 GPIO；
6. KEYMNG 根据连续按下次数识别短按和长按；
7. KEYMNG 通过 EventHub 发布按键事件；
8. UI 层订阅按键事件，并执行拍照、启停录像、关机或恢复出厂设置。

完整调用线路：

```text
实体按键电平
    │
    ▼
Hi3516CV610 GPIO 寄存器
    │
    ▼
ss_gpio_read_bit()
    │
    ▼
gpio_ioctl(GPIO_READ_BIT)
    │
    ▼
/dev/ot_gpio
    │
    ▼
HAL_GPIO_GetBitVal()
    │
    ▼
HAL_KEY_GetGpioState()
    │
    ▼
SS_HAL_KEY_GetState()
    │
    ▼
KEYMNG_ClickCheck()，每 200 ms 调用
    │
    ▼
SS_EVTHUB_Publish()
    │
    ▼
PDT_UI_EventDispatchOnEvent()
    │
    ▼
PDT_UI_ProcStateMsgCallback()
    │
    ▼
PDT_UI_ProcKeyEvents()
    │
    ├── 拍照
    ├── 开始/停止录像
    ├── 关机
    └── 恢复出厂设置
```

---

## 2. 驱动层：注册 `/dev/ot_gpio`

### 2.1 ioctl 命令定义

源文件：

```text
source/camera/driver/gpio/ss_gpio.h
```

关键代码：

```c
typedef struct {
    unsigned int group_num;
    unsigned int bit_num;
    unsigned int value;
} ot_gpio_groupbit_info;

typedef struct {
    unsigned char pin;
    unsigned char dir;
    unsigned int value;
} ot_gpio_data;

#define GPIO_SET_DIR   _IOWR('w', 4, ot_gpio_data)
#define GPIO_GET_DIR   _IOWR('r', 5, ot_gpio_data)
#define GPIO_READ_BIT  _IOWR('r', 6, ot_gpio_data)
#define GPIO_WRITE_BIT _IOWR('w', 7, ot_gpio_data)

int ss_gpio_set_dir(const ot_gpio_groupbit_info *grp_bit_info);
int ss_gpio_get_dir(ot_gpio_groupbit_info *grp_bit_info);
int ss_gpio_write_bit(const ot_gpio_groupbit_info *grp_bit_info);
int ss_gpio_read_bit(ot_gpio_groupbit_info *grp_bit_info);
```

按键读取主要使用：

```text
GPIO_SET_DIR  ：将对应 GPIO 设置为输入
GPIO_READ_BIT ：读取对应 GPIO 的当前电平
```

### 2.2 注册字符设备

源文件：

```text
source/camera/driver/gpio/ss_gpio.c
```

关键代码：

```c
static const struct file_operations g_gpio_fops = {
    .owner = THIS_MODULE,
    .open  = gpio_open,
#if (LINUX_VERSION_CODE < KERNEL_VERSION(2, 6, 36))
    .ioctl = gpio_ioctl,
#else
    .unlocked_ioctl = gpio_ioctl,
#endif
    .release = gpio_release,
};

static struct miscdevice g_gpio_dev = {
    .minor = MISC_DYNAMIC_MINOR,
    .name = "ot_gpio",
    .fops = &g_gpio_fops,
};

static int __init ss_gpio_init(void)
{
    int ret = misc_register(&g_gpio_dev);
    if (ret != 0) {
        printk(KERN_ERR "register misc dev for gpio fail!\n");
        return ret;
    }
    return 0;
}
```

驱动加载成功后，Linux 中出现：

```text
/dev/ot_gpio
```

用户态并不直接访问 GPIO 物理地址，而是打开这个设备，并通过 `ioctl` 请求驱动读写寄存器。

### 2.3 ioctl 分发

关键代码：

```c
static long gpio_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
    ot_gpio_groupbit_info group_bit_info;
    uintptr_t argv = (uintptr_t)arg;
    long ret;

    if (argv == 0) {
        return -1;
    }

    switch (_IOC_NR(cmd)) {
        case _IOC_NR(GPIO_SET_DIR):
            ret = copy_from_user(&group_bit_info,
                (ot_gpio_groupbit_info *)argv,
                sizeof(ot_gpio_groupbit_info));
            ioctl_return_if_fail(ret);

            ret = ss_gpio_set_dir(&group_bit_info);
            ioctl_return_if_fail(ret);
            break;

        case _IOC_NR(GPIO_GET_DIR):
            ret = copy_from_user(&group_bit_info,
                (ot_gpio_groupbit_info *)argv,
                sizeof(ot_gpio_groupbit_info));
            ioctl_return_if_fail(ret);

            ret = ss_gpio_get_dir(&group_bit_info);
            ioctl_return_if_fail(ret);

            ret = copy_to_user((void __user *)argv,
                &group_bit_info,
                sizeof(ot_gpio_groupbit_info));
            ioctl_return_if_fail(ret);
            break;

        case _IOC_NR(GPIO_READ_BIT):
            ret = copy_from_user(&group_bit_info,
                (ot_gpio_groupbit_info *)argv,
                sizeof(ot_gpio_groupbit_info));
            ioctl_return_if_fail(ret);

            ret = ss_gpio_read_bit(&group_bit_info);
            ioctl_return_if_fail(ret);

            ret = copy_to_user((void __user *)argv,
                &group_bit_info,
                sizeof(ot_gpio_groupbit_info));
            ioctl_return_if_fail(ret);
            break;

        case _IOC_NR(GPIO_WRITE_BIT):
            ret = copy_from_user(&group_bit_info,
                (ot_gpio_groupbit_info *)argv,
                sizeof(ot_gpio_groupbit_info));
            ioctl_return_if_fail(ret);

            ret = ss_gpio_write_bit(&group_bit_info);
            ioctl_return_if_fail(ret);
            break;

        default:
            return -1;
    }
    return 0;
}
```

`copy_from_user()` 把用户态传入的 GPIO 组号、位号复制到内核空间；读取完成后，`copy_to_user()` 再把电平值复制回用户态。

### 2.4 驱动读取 GPIO 寄存器

GPIO 输入方向设置：

```c
int ss_gpio_set_dir(const ot_gpio_groupbit_info *grp_bit_info)
{
    unsigned int reg_value;

    mutex_lock(&g_mutex_lock);
    if (gpio_preproc_param(grp_bit_info) != 0) {
        mutex_unlock(&g_mutex_lock);
        return -1;
    }

    reg_value = gpio_read_reg(GPIO_DIR_BASE);
    if (grp_bit_info->value == 0) {
        reg_value = gpio_clear_bit(reg_value, grp_bit_info->bit_num);
    } else if (grp_bit_info->value == 1) {
        reg_value = gpio_set_bit(reg_value, grp_bit_info->bit_num);
    } else {
        printk("dir beyond of extent!\n");
        mutex_unlock(&g_mutex_lock);
        return -1;
    }

    gpio_write_reg(GPIO_DIR_BASE, reg_value);
    mutex_unlock(&g_mutex_lock);
    return 0;
}
```

GPIO 电平读取：

```c
int ss_gpio_read_bit(ot_gpio_groupbit_info *grp_bit_info)
{
    unsigned int reg_value;

    mutex_lock(&g_mutex_lock);
    if (gpio_preproc_param(grp_bit_info) != 0) {
        mutex_unlock(&g_mutex_lock);
        return -1;
    }

    reg_value = gpio_read_reg(GPIO_DATA_BASE);
    reg_value = gpio_get_bit(reg_value, grp_bit_info->bit_num);
    grp_bit_info->value = ((reg_value != 0) ? 1 : 0);

    mutex_unlock(&g_mutex_lock);
    return 0;
}
```

Hi3516CV610 各 GPIO 组物理基地址来自：

```text
source/camera/driver/gpio/gpio_grpinfo_hi3516cv610.h
```

例如 GPIO0 的物理基地址为：

```c
static ot_gpio_grp_info_s g_gpio_grp_info[] = {
    { 0, 0x11090000, 0x0 },
    { 1, 0x11091000, 0x0 },
    { 2, 0x11092000, 0x0 },
    /* ... */
};
```

所以 GPIO0_0、GPIO0_7 最终都从 GPIO0 控制器对应的数据寄存器读取。

---

## 3. 通用 GPIO HAL：把驱动 ioctl 封装成函数

源文件：

```text
source/camera/hal/common/src/hal_gpio.c
```

### 3.1 打开 GPIO 设备

```c
#ifdef __LITEOS__
#define HAL_GPIO_DEV "/dev/gpio"
#else
#define HAL_GPIO_DEV "/dev/ot_gpio"
#endif

td_s32 HAL_GPIO_Init(td_s32 *fd)
{
    if (fd == TD_NULL) {
        MLOGE("input fd is null\n");
        return TD_FAILURE;
    }

    td_s32 tmpFd = open(HAL_GPIO_DEV, O_RDWR);
    if (tmpFd < 0) {
        MLOGE("open gpiodev failed\n");
        return TD_FAILURE;
    }

    *fd = tmpFd;
    return TD_SUCCESS;
}
```

HC101 当前是 Linux，所以打开的是 `/dev/ot_gpio`。

### 3.2 设置 GPIO 输入方向

```c
td_s32 HAL_GPIO_SetDir(td_s32 fd, td_u32 grpNum,
    td_u32 bitNum, GPIO_Dir dirVal)
{
    td_s32 ret;

    if (grpNum >= HAL_GPIO_GRPNUM_MAX ||
        bitNum >= HAL_GPIO_BITNUM_MAX) {
        MLOGE("gpio param(grp:%u,bit:%u) is illegal\n",
            grpNum, bitNum);
        return TD_FAILURE;
    }

    if (fd <= HAL_FD_INITIALIZATION_VAL) {
        MLOGE("gpio fd(%d) is illegal\n", fd);
        return TD_FAILURE;
    }

    if ((dirVal != GPIO_DIR_READ) &&
        (dirVal != GPIO_DIR_WRITE)) {
        MLOGE("dirVal(%u) illegal\n", dirVal);
        return TD_FAILURE;
    }

    ot_gpio_groupbit_info gpioData = {0};
    gpioData.group_num = grpNum;
    gpioData.bit_num = bitNum;
    gpioData.value = dirVal;

    ret = ioctl(fd, GPIO_SET_DIR, &gpioData);
    if (ret != TD_SUCCESS) {
        MLOGE("gpio set dir failed\n");
        return TD_FAILURE;
    }

    return TD_SUCCESS;
}
```

### 3.3 读取 GPIO 电平

```c
td_s32 HAL_GPIO_GetBitVal(td_s32 fd, td_u32 grpNum,
    td_u32 bitNum, td_u32 *bitVal)
{
    if (bitVal == TD_NULL) {
        MLOGE("pointer is null!\n");
        return OT_HAL_EINVAL;
    }

    if (fd <= HAL_FD_INITIALIZATION_VAL) {
        MLOGE("gpio fd(%d) is illegal\n", fd);
        return TD_FAILURE;
    }

    if (grpNum >= HAL_GPIO_GRPNUM_MAX ||
        bitNum >= HAL_GPIO_BITNUM_MAX) {
        MLOGE("gpio param(grp:%u,bit:%u) is illegal\n",
            grpNum, bitNum);
        return TD_FAILURE;
    }

    ot_gpio_groupbit_info gpioData = {0};
    gpioData.group_num = grpNum;
    gpioData.bit_num = bitNum;

    td_s32 ret = ioctl(fd, GPIO_READ_BIT, &gpioData);
    if (ret != TD_SUCCESS) {
        MLOGE("gpio read bit failed\n");
        return TD_FAILURE;
    }

    *bitVal = gpioData.value;
    return TD_SUCCESS;
}
```

这一层负责把 `/dev/ot_gpio`、`ioctl` 和数据结构隐藏起来，上层只需要传递 GPIO 组号、位号即可。

---

## 4. 板级层：定义 HC101 的两个按键 GPIO

源文件：

```text
source/camera/demo/dronecam/modules/init/smp/src/board/hi3516cv610_demb.c
```

关键代码：

```c
static td_s32 PDT_BOARD_KeyRegister(td_void)
{
    td_s32 ret;
    OT_KEY_Obj obj = {0};
    td_s32 idx;

    /* 管脚复用 */
    OT_WriteReg(0x10260000, 0x1100); /* GPIO0_0 */
    OT_WriteReg(0x11130034, 0x1206); /* GPIO0_7 */

    for (idx = 0; idx < OT_KEY_IDX_BUTT; idx++) {
        obj.cfg[idx].type = OT_KEY_SRC_TYPE_BUTT;
    }

    obj.cnt = 2;

    obj.cfg[OT_KEY_IDX_0].type = OT_KEY_SRC_TYPE_GPIO;
    obj.cfg[OT_KEY_IDX_0].cfg.gpioCfg.grp = 0;
    obj.cfg[OT_KEY_IDX_0].cfg.gpioCfg.bit = 0;

    obj.cfg[OT_KEY_IDX_1].type = OT_KEY_SRC_TYPE_GPIO;
    obj.cfg[OT_KEY_IDX_1].cfg.gpioCfg.grp = 0;
    obj.cfg[OT_KEY_IDX_1].cfg.gpioCfg.bit = 7;

    /* 设置为输入方向 */
    td_u32 tmpvalue;
    OT_ReadReg(0x11090400, &tmpvalue);
    tmpvalue &= ~(0x1 << 0);
    OT_WriteReg(0x11090400, tmpvalue);

    OT_ReadReg(0x11090400, &tmpvalue);
    tmpvalue &= ~(0x1 << 7);
    OT_WriteReg(0x11090400, tmpvalue);

    ret = SS_HAL_KEY_Register(&obj);
    if (ret != TD_SUCCESS) {
        MLOGE("key register error [%x]\n", ret);
        return TD_FAILURE;
    }

    MLOGI("#######regitser ok\n");
    return TD_SUCCESS;
}
```

板级外设注册函数调用它：

```c
td_s32 PDT_BOARD_PeripheralRegister(td_void)
{
    td_s32 ret;

    /* 其他外设初始化省略 */

    ret = PDT_BOARD_KeyRegister();
    if (ret != TD_SUCCESS) {
        MLOGE("PDT_BOARD_KeyRegister failed\n");
        return TD_FAILURE;
    }

    /* 其他外设初始化省略 */
    return TD_SUCCESS;
}
```

最外层入口位于：

```text
source/camera/demo/dronecam/modules/init/smp/src/ss_product_init_peripheral.c
```

```c
td_s32 SS_PDT_INIT_PERIPHERAL_Init(td_void)
{
    td_s32 ret;

    MLOGI("-->peripheral init ...\n");
    ret = PDT_BOARD_PeripheralRegister();
    OT_APPCOMM_RETURN_IF_FAIL(ret, TD_FAILURE);

    return TD_SUCCESS;
}
```

这一阶段完成的是：

```text
物理管脚 → 按键索引

GPIO0_0 → OT_KEY_IDX_0
GPIO0_7 → OT_KEY_IDX_1
```

---

## 5. 按键 HAL：把 GPIO 电平转换成按下/松开状态

源文件：

```text
source/camera/hal/key/src/ss_hal_key.c
```

### 5.1 保存板级按键描述

```c
typedef struct {
    td_bool registered;
    td_bool isInitialized;
    td_s32 gpioFd;
    td_s32 adcInit;
    OT_KEY_Obj obj;
} OT_KEY_Ctx;

OT_KEY_Ctx g_keyCtx = {
    TD_FALSE,
    TD_FALSE,
    HAL_FD_INITIALIZATION_VAL,
    0,
    {}
};

td_s32 SS_HAL_KEY_Register(const OT_KEY_Obj *obj)
{
    if (g_keyCtx.registered == TD_TRUE) {
        MLOGE("key has been registereded\n");
        return SS_HAL_EREGRED;
    }

    if ((obj == TD_NULL) || (obj->cnt > OT_KEY_IDX_BUTT)) {
        MLOGE("registerede param fail\n");
        return SS_HAL_EINVAL;
    }

    g_keyCtx.obj = *obj;
    g_keyCtx.registered = TD_TRUE;
    return TD_SUCCESS;
}
```

### 5.2 初始化按键 GPIO 设备

```c
static td_s32 HAL_KEY_GpioInit(td_void)
{
    if (g_keyCtx.gpioFd != HAL_FD_INITIALIZATION_VAL) {
        MLOGW("gpio key already init,other gpio key need not init\n");
        return TD_SUCCESS;
    }

    td_s32 ret = HAL_GPIO_Init(&g_keyCtx.gpioFd);
    if (ret == TD_FAILURE) {
        MLOGE("open gpiodev failed,errno(%d)\n", errno);
        return SS_HAL_EINTER;
    }

    return TD_SUCCESS;
}

td_s32 SS_HAL_KEY_Init(td_void)
{
    td_s32 ret;

    if (g_keyCtx.registered == TD_FALSE) {
        MLOGE("key has not been registereded\n");
        return SS_HAL_ENOREG;
    }

    if (g_keyCtx.isInitialized == TD_TRUE) {
        MLOGW("key has already init\n");
        return TD_SUCCESS;
    }

    for (td_u32 i = 0; i < g_keyCtx.obj.cnt; i++) {
        if (g_keyCtx.obj.cfg[i].type == OT_KEY_SRC_TYPE_GPIO) {
            ret = HAL_KEY_GpioInit();
        } else if (g_keyCtx.obj.cfg[i].type == OT_KEY_SRC_TYPE_ADC) {
            ret = HAL_KEY_AdcInit(&g_keyCtx.obj.cfg[i].cfg.adcCfg);
        } else if (g_keyCtx.obj.cfg[i].type == OT_KEY_SRC_TYPE_PMC) {
            ret = TD_SUCCESS;
        } else {
            MLOGE("idx[%u],type[%u] is not valid\n",
                i, g_keyCtx.obj.cfg[i].type);
            ret = TD_FAILURE;
        }

        if (ret != TD_SUCCESS) {
            HAL_KEY_Deinit();
            return ret;
        }
    }

    g_keyCtx.isInitialized = TD_TRUE;
    return TD_SUCCESS;
}
```

两个 GPIO 按键共用同一个 `/dev/ot_gpio` 文件描述符。

### 5.3 读取指定按键 GPIO

```c
static td_s32 HAL_KEY_GetGpioState(
    OT_KEY_Gpio *gpioCfg, td_u32 *value)
{
    td_s32 ret;

    ret = HAL_GPIO_SetDir(g_keyCtx.gpioFd,
        gpioCfg->grp, gpioCfg->bit, GPIO_DIR_READ);
    if (ret != TD_SUCCESS) {
        MLOGE("set gpio dir failed\n");
        return SS_HAL_EGPIO;
    }

    ret = HAL_GPIO_GetBitVal(g_keyCtx.gpioFd,
        gpioCfg->grp, gpioCfg->bit, value);
    if (ret != TD_SUCCESS) {
        MLOGE("read gpio data failed\n");
        return SS_HAL_EGPIO;
    }

    /* GPIO0_7 的有效电平与另一个按键相反 */
    if (gpioCfg->bit == 7) {
        if (*value == 0) {
            *value = 1;
        } else {
            *value = 0;
        }
    }

    return TD_SUCCESS;
}
```

### 5.4 转换成统一按键状态

```c
td_s32 SS_HAL_KEY_GetState(OT_KEY_Idx idx, OT_KEY_State *state)
{
    td_u32 value = 0;
    td_s32 ret = TD_FAILURE;

    if (g_keyCtx.registered == TD_FALSE) {
        return SS_HAL_ENOREG;
    }

    if (g_keyCtx.isInitialized == TD_FALSE) {
        return SS_HAL_ENOINIT;
    }

    if ((state == TD_NULL) || (idx >= OT_KEY_IDX_BUTT)) {
        return SS_HAL_EINVAL;
    }

    if (g_keyCtx.obj.cfg[idx].type == OT_KEY_SRC_TYPE_GPIO) {
        ret = HAL_KEY_GetGpioState(
            &g_keyCtx.obj.cfg[idx].cfg.gpioCfg, &value);
    } else if (g_keyCtx.obj.cfg[idx].type == OT_KEY_SRC_TYPE_ADC) {
        ret = HAL_KEY_GetAdcState(
            &g_keyCtx.obj.cfg[idx].cfg.adcCfg, &value);
    } else if (g_keyCtx.obj.cfg[idx].type == OT_KEY_SRC_TYPE_PMC) {
        ret = HAL_KEY_GetPmcState(&value);
    }

    if (ret == TD_SUCCESS) {
        *state = (OT_KEY_State)((value == 1) ?
            OT_KEY_STATE_UP : OT_KEY_STATE_DOWN);
        return TD_SUCCESS;
    }

    return TD_FAILURE;
}
```

统一状态定义：

```c
typedef enum {
    OT_KEY_STATE_DOWN = 0, /* 按下 */
    OT_KEY_STATE_UP,       /* 松开 */
    OT_KEY_STATE_BUTT
} OT_KEY_State;
```

电平关系如下：

| 按键 | 原始 GPIO 电平 | HAL 是否反相 | 最终状态 |
|---|---:|---:|---|
| GPIO0_0 | 0 | 否 | `DOWN` |
| GPIO0_0 | 1 | 否 | `UP` |
| GPIO0_7 | 0 | 是 | `UP` |
| GPIO0_7 | 1 | 是 | `DOWN` |

---

## 6. 参数层：配置按键类型和逻辑 ID

X10 配置文件：

```text
source/camera/demo/dronecam/modules/param/inicfg/
hi3516cv610/nonescreen/gc4653_ahd_128M_X10/
config_product_devmng.ini
```

配置内容：

```ini
[keymng.key]
key_cnt            = "2"
key_type0          = "0"
key_id0            = "0"
longkey_enable0    = "1"
longkey_time0      = "2000"
key_type1          = "0"
key_id1            = "1"
longkey_enable1    = "1"
longkey_time1      = "2000"

[keymng.grpkey]
enable             = "0"
key_idx0           = "0"
key_idx1           = "1"
```

含义：

| 配置项 | 含义 |
|---|---|
| `key_cnt=2` | 有两个逻辑按键 |
| `key_type=0` | click 类型，需要判断短按/长按 |
| `key_id0=0` | 第0个物理按键发布事件时使用逻辑 ID 0 |
| `key_id1=1` | 第1个物理按键发布事件时使用逻辑 ID 1 |
| `longkey_enable=1` | 开启长按判断 |
| `longkey_time=2000` | 长按阈值配置为 2000 ms |
| `grpkey.enable=0` | 不启用组合按键 |

INI 转换阶段把它加载到 `OT_KEYMNG_Cfg`：

```c
ret = PDT_INIPARAM_LoadIntValueByNodePrefix(
    iniModule, "keymng.key", "key_cnt", 0,
    (td_s32 *)&param->keyCfg.keyCnt);

for (idx = 0; idx < param->keyCfg.keyCnt; ++idx) {
    /* 加载 key_typeX */
    ret = sprintf_s(iniNodeName,
        PDT_INIPARAM_NODE_NAME_LEN,
        "keymng.key:key_type%u", idx);
    ret = SS_CONFACCESS_GetInt(
        PDT_INIPARAM, iniModule, iniNodeName, 0,
        (td_s32 *)&param->keyCfg.attr[idx].type);

    /* 加载 key_idX */
    ret = sprintf_s(iniNodeName,
        PDT_INIPARAM_NODE_NAME_LEN,
        "keymng.key:key_id%u", idx);
    ret = SS_CONFACCESS_GetInt(
        PDT_INIPARAM, iniModule, iniNodeName, 0,
        &param->keyCfg.attr[idx].id);

    if (param->keyCfg.attr[idx].type ==
        OT_KEYMNG_KEY_TYPE_CLICK) {
        /* 加载 longkey_enableX 和 longkey_timeX */
    }
}
```

运行时由参数模块提供：

```c
td_s32 SS_PDT_PARAM_GetKeyMngCfg(OT_KEYMNG_Cfg *cfg)
{
    return PDT_PARAM_GetKeyMngCfg(cfg);
}

td_s32 PDT_PARAM_GetKeyMngCfg(OT_KEYMNG_Cfg *cfg)
{
    OT_APPCOMM_RETURN_IF_PTR_NULL(cfg, OT_PARAM_EINVAL);
    OT_APPCOMM_RETURN_IF_EXPR_FALSE(
        PDT_PARAM_IsInited(), OT_PARAM_ENOTINIT);

    SS_PARAM2FLASH_Lock();
    *cfg = PDT_PARAM_GetCfg()->devMngCfg.keyMngCfg;
    SS_PARAM2FLASH_Unlock();

    PDT_PARAM_DebugKeyMngCfg(cfg);
    return TD_SUCCESS;
}
```

---

## 7. KEYMNG：轮询按键并识别短按/长按

源文件：

```text
source/camera/component/devmng/src/ss_keymng.c
```

### 7.1 应用启动按键管理

源文件：

```text
source/camera/demo/dronecam/modules/init/smp/src/ss_product_main.c
```

```c
static td_void InitKeymng(td_void)
{
    td_s32 ret;
    OT_KEYMNG_Cfg keyCfg;

    ret = SS_PDT_PARAM_GetKeyMngCfg(&keyCfg);
    OT_APPCOMM_LOG_IF_FAIL(ret,
        "CAM_PDT_PARAM_GetKeyMngCfg");

    ret = SS_KEYMNG_Init(&keyCfg);
    OT_APPCOMM_LOG_IF_FAIL(ret, "CAM_KEYMNG_Init");

    MLOGI("%s: %u ms keyCnt:%d\n",
        "key available", SS_TIMESTAMP_GetMs(),
        keyCfg.keyCfg.keyCnt);
}
```

`SS_KEYMNG_Init()` 初始化按键 HAL，并创建轮询线程：

```c
td_s32 SS_KEYMNG_Init(const OT_KEYMNG_Cfg *cfg)
{
    td_s32 ret;

    if (!KEYMNG_ParamValidChck(cfg)) {
        MLOGE("parm check error\n");
        return OT_KEYMNG_EINVAL;
    }

    OT_MUTEX_LOCK(g_keymngCtx.mutex);

    if (g_keymngCtx.isInitialized) {
        OT_MUTEX_UNLOCK(g_keymngCtx.mutex);
        return OT_KEYMNG_EINITIALIZED;
    }

    ret = SS_HAL_KEY_Init();
    if (ret != TD_SUCCESS) {
        MLOGE("SS_HAL_KEY_Init Failed\n");
        OT_MUTEX_UNLOCK(g_keymngCtx.mutex);
        return OT_KEYMNG_EINTER;
    }

    KEYMNG_ParamInit(cfg);
    g_keymngCtx.checkTskRun = TD_TRUE;

    ret = pthread_create(&g_keymngCtx.checkTskId,
        TD_NULL, KEYMNG_CheckThread, TD_NULL);
    if (ret != TD_SUCCESS) {
        MLOGE("Create KeyCheck Thread Fail!\n");
        SS_HAL_KEY_Deinit();
        OT_MUTEX_UNLOCK(g_keymngCtx.mutex);
        return OT_KEYMNG_ETHREAD;
    }

    g_keymngCtx.isInitialized = TD_TRUE;
    OT_MUTEX_UNLOCK(g_keymngCtx.mutex);
    return TD_SUCCESS;
}
```

### 7.2 每 200 ms 轮询

```c
#define KEYMNG_CHECK_INTERVAL 200

static td_void *KEYMNG_CheckThread(td_void *data)
{
    MLOGD("thread KEY_CHECK enter\n");
    prctl(PR_SET_NAME, "KEY_CHECK", 0, 0, 0);

    while (g_keymngCtx.checkTskRun) {
        KEYMNG_KeyCheck(&g_keymngInfoSet);
        SS_Usleep(KEYMNG_CHECK_INTERVAL * 1000);
    }

    MLOGD("thread KEY_CHECK exit\n");
    return TD_NULL;
}

static td_void KEYMNG_KeyCheck(KEYMNG_InfoSet *infoSet)
{
    td_u32 i;

    for (i = 0; i < infoSet->keyCnt; ++i) {
        if (infoSet->keyInfo[i].attr.type ==
            OT_KEYMNG_KEY_TYPE_CLICK) {
            KEYMNG_ClickCheck(i, &infoSet->keyInfo[i]);
        } else {
            KEYMNG_HoldCheck(i, &infoSet->keyInfo[i]);
        }
    }

    if (infoSet->grpKeyCfg.enable) {
        KEYMNG_GroupKeyCheck(infoSet);
    }
}
```

### 7.3 识别短按和长按

当前代码的关键逻辑：

```c
static td_void KEYMNG_ClickCheck(
    OT_KEY_Idx idx, KEYMNG_Info *clickInfo)
{
    /* 未产测时屏蔽按键1，避免与串口 IO 冲突 */
    if (idx == OT_KEY_IDX_1 &&
        !SS_TESTMNG_IsFactoryTested()) {
        MLOGI("未产测，屏蔽按键1\n");
        return;
    }

    OT_KEY_State keyState = OT_KEY_STATE_UP;
    OT_EVENT_S event;

    td_u32 longClickCnt =
        clickInfo->attr.attr.clickAttr.longClickTimeMsec /
        KEYMNG_CHECK_INTERVAL;

    td_u32 long3sClickCnt =
        2000 / KEYMNG_CHECK_INTERVAL;

    td_u32 long8sClickCnt =
        5000 / KEYMNG_CHECK_INTERVAL;

    SS_HAL_KEY_GetState(idx, &keyState);

    if (keyState == OT_KEY_STATE_DOWN) {
        clickInfo->halKeyState = OT_KEY_STATE_DOWN;
        clickInfo->keyDownCnt++;
    } else {
        if (clickInfo->halKeyState == OT_KEY_STATE_DOWN) {
            clickInfo->halKeyState = OT_KEY_STATE_UP;

            if ((clickInfo->keyDownCnt < longClickCnt) &&
                !clickInfo->multiKeyFound) {
                event.EventID = OT_EVENT_KEYMNG_SHORT_CLICK;
                event.arg1 = clickInfo->attr.id;
                SS_EVTHUB_Publish(&event);
                MLOGI("short click event[%u]\n",
                    clickInfo->attr.id);
            } else {
                if ((clickInfo->keyDownCnt >= long3sClickCnt) &&
                    !clickInfo->multiKeyFound) {
                    event.EventID =
                        OT_EVENT_KEYMNG_LONG_CLICK3S;
                    event.arg1 = clickInfo->attr.id;
                    SS_EVTHUB_Publish(&event);
                    MLOGI("long click 3s event[%u]\n",
                        clickInfo->attr.id);
                }
            }

            clickInfo->keyDownCnt = 0;
            clickInfo->multiKeyFound = TD_FALSE;
        }
    }
}
```

时间计算：

```text
轮询周期             = 200 ms
X10 longkey_time     = 2000 ms
长按判断次数          = 2000 / 200 = 10 次
```

因此当前 X10 实际上是：

- 按住少于约 2 秒后松开：发布短按事件；
- 按住达到约 2 秒后松开：发布 `LONG_CLICK3S` 事件。

注意：事件名称叫 `LONG_CLICK3S`，但代码里的阈值是 2000 ms；而且事件是在松开按键时才发布。

### 7.4 EventHub 事件定义和注册

源文件：

```text
source/camera/component/devmng/include/ss_keymng.h
```

```c
typedef enum {
    OT_EVENT_KEYMNG_SHORT_CLICK =
        OT_REF_EVENT_ID(OT_REF_MOD_KEYMNG, 0),
    OT_EVENT_KEYMNG_LONG_CLICK3S,
    OT_EVENT_KEYMNG_LONG_CLICK5S,
    OT_EVENT_KEYMNG_HOLD_DOWN,
    OT_EVENT_KEYMNG_HOLD_UP,
    OT_EVENT_KEYMNG_GROUP,
    OT_EVENT_KEYMNG_BUIT
} OT_KEYMNG_EventId;
```

初始化时注册事件 ID：

```c
td_s32 SS_KEYMNG_RegisterEvent(td_void)
{
    td_s32 ret;

    ret = SS_EVTHUB_Register(OT_EVENT_KEYMNG_SHORT_CLICK);
    OT_APPCOMM_RETURN_IF_FAIL(ret,
        OT_KEYMNG_EREGISTEREVENT);

    ret = SS_EVTHUB_Register(OT_EVENT_KEYMNG_LONG_CLICK3S);
    OT_APPCOMM_RETURN_IF_FAIL(ret,
        OT_KEYMNG_EREGISTEREVENT);

    ret = SS_EVTHUB_Register(OT_EVENT_KEYMNG_LONG_CLICK5S);
    OT_APPCOMM_RETURN_IF_FAIL(ret,
        OT_KEYMNG_EREGISTEREVENT);

    ret = SS_EVTHUB_Register(OT_EVENT_KEYMNG_HOLD_DOWN);
    OT_APPCOMM_RETURN_IF_FAIL(ret,
        OT_KEYMNG_EREGISTEREVENT);

    ret = SS_EVTHUB_Register(OT_EVENT_KEYMNG_HOLD_UP);
    OT_APPCOMM_RETURN_IF_FAIL(ret,
        OT_KEYMNG_EREGISTEREVENT);

    ret = SS_EVTHUB_Register(OT_EVENT_KEYMNG_GROUP);
    OT_APPCOMM_RETURN_IF_FAIL(ret,
        OT_KEYMNG_EREGISTEREVENT);

    return TD_SUCCESS;
}
```

应用主初始化表中包含：

```c
static td_s32 (*g_registerEventOps[])(td_void) = {
    SS_STORAGEMNG_RegisterEvent,
    SS_RECMNG_RegisterEvent,
    SS_PHOTOMNG_RegisterEvent,
    SS_FILEMNG_RegisterEvent,
    SS_PDT_STATEMNG_RegisterEvent,
    SS_KEYMNG_RegisterEvent,
    /* ... */
};
```

---

## 8. UI 事件订阅和分发

### 8.1 UI 订阅按键事件

源文件：

```text
source/camera/demo/dronecam/modules/ui/nonescreen/src/ss_product_ui.c
```

UI 事件列表中包含：

```c
static const OT_EVENT_ID g_eventList[] = {
    /* 存储等其他事件省略 */
    OT_EVENT_KEYMNG_SHORT_CLICK,
    OT_EVENT_KEYMNG_LONG_CLICK3S,
    OT_EVENT_KEYMNG_LONG_CLICK5S,
    /* 其他事件省略 */
};
```

UI 初始化时订阅这些事件：

```c
td_s32 SS_PDT_UI_Init(td_void)
{
    td_s32 ret;

    ret = PDT_UI_EventInit(
        g_eventList,
        ARRAY_SIZE(g_eventList),
        PDT_UI_ProcStateMsgCallback);

    OT_APPCOMM_LOG_AND_RETURN_IF_FAIL(
        ret, ret, "UI_EventInit");

    /* 其他 UI 初始化省略 */
    return TD_SUCCESS;
}
```

### 8.2 EventHub 创建订阅者

源文件：

```text
source/camera/demo/dronecam/modules/ui/modules/ui_event_dispatch.c
```

```c
static td_s32 PDT_UI_EventDispatchOnEvent(
    const OT_EVENT_S *event, const td_void *argv)
{
    td_s32 ret;

    MLOGD("EventID:%#x, arg1:%#x, arg2:%#x, result:%d\n",
        event->EventID, event->arg1,
        event->arg2, event->s32Result);

    if (g_eventDispatchCtx.eventDispatcher != TD_NULL) {
        ret = g_eventDispatchCtx.eventDispatcher(event);
        OT_APPCOMM_RETURN_IF_FAIL(ret, TD_FAILURE);
    } else {
        return TD_FAILURE;
    }

    return TD_SUCCESS;
}

td_s32 PDT_UI_EventInit(
    const td_u32 *eventList,
    td_u32 eventCount,
    UI_EventProcFuncPtr eventHubProcFuncPtr)
{
    OT_SUBSCRIBER_S subscriber = {
        .azName = { "UIEvent" },
        .SS_EVTHUB_EVENTPROC_FN_PTR =
            PDT_UI_EventDispatchOnEvent,
        .argv = TD_NULL,
        .bSync = TD_FALSE
    };

    td_s32 ret = SS_EVTHUB_CreateSubscriber(
        &subscriber,
        &g_eventDispatchCtx.subscriberHdl);
    if (ret != TD_SUCCESS) {
        return TD_FAILURE;
    }

    for (td_u32 i = 0; i < eventCount; i++) {
        ret = SS_EVTHUB_Subscribe(
            g_eventDispatchCtx.subscriberHdl,
            eventList[i]);
        if (ret != TD_SUCCESS) {
            continue;
        }

        g_eventDispatchCtx.eventList[
            g_eventDispatchCtx.eventCount] = eventList[i];
        g_eventDispatchCtx.eventCount++;
    }

    g_eventDispatchCtx.eventDispatcher =
        eventHubProcFuncPtr;
    return TD_SUCCESS;
}
```

`.bSync = TD_FALSE` 表示 UI EventHub 订阅者采用异步处理方式，按键检测线程负责发布事件，但最终业务处理不直接在 KEY_CHECK 线程中完成。

### 8.3 UI 根据 EventID 查找处理函数

```c
static UI_HomeEventFuncInfo g_homeStateEventsFuncInfo[] = {
    {
        OT_EVENT_KEYMNG_SHORT_CLICK,
        PDT_UI_ProcKeyEvents
    },
    {
        OT_EVENT_KEYMNG_LONG_CLICK3S,
        PDT_UI_ProcKeyEvents
    },
    {
        OT_EVENT_KEYMNG_LONG_CLICK5S,
        PDT_UI_ProcKeyEvents
    },
    /* 其他事件省略 */
};
```

EventHub 回调最终执行：

```c
static td_s32 PDT_UI_ProcStateMsgCallback(
    const OT_EVENT_S *event)
{
    OT_STATEMNG_WorkModeState workModeState = {0};
    td_s32 ret;

    ret = SS_PDT_STATEMNG_GetState(&workModeState);
    OT_APPCOMM_RETURN_IF_FAIL(ret, TD_FAILURE);

    td_u32 i;
    td_bool found = TD_FALSE;

    for (i = 0;
        i < ARRAY_SIZE(g_homeStateEventsFuncInfo);
        i++) {
        if (g_homeStateEventsFuncInfo[i].eventID ==
            event->EventID) {
            found = TD_TRUE;
            break;
        }
    }

    if (!found) {
        return TD_FAILURE;
    }

    ret = g_homeStateEventsFuncInfo[i].dealFunc(
        event, &workModeState);
    OT_APPCOMM_RETURN_IF_FAIL(ret, TD_FAILURE);

    return TD_SUCCESS;
}
```

---

## 9. 应用业务层：按键最终执行什么功能

处理函数：

```text
PDT_UI_ProcKeyEvents()
```

源文件：

```text
source/camera/demo/dronecam/modules/ui/nonescreen/src/ss_product_ui.c
```

### 9.1 进入业务前的限制

APP 已连接时屏蔽大部分实体按键：

```c
if (PDT_NETCTRL_IsClientConnecting()) {
    if ((event->arg1 == OT_KEY_IDX_1) &&
        (event->EventID ==
            OT_EVENT_KEYMNG_LONG_CLICK3S)) {
        MLOGI("app is connect,long key idx 1\n");
    } else {
        MLOGI("app is connect return\n");
        return TD_SUCCESS;
    }
}
```

停车缩时录像或停车唤醒状态也会屏蔽按键：

```c
OT_SYSTEM_StartupSource startupSrc =
    OT_SYSTEM_STARTUP_SRC_STARTUP;

SS_SYSTEM_GetStartupWakeUpSource(&startupSrc);

if (g_homePageContext.laspeInfo.inParkingLaspe ||
    (startupSrc == OT_SYSTEM_STARTUP_SRC_WAKEUP)) {
    MLOGI("acc off or parking :%d, return\n", startupSrc);
    return TD_SUCCESS;
}
```

### 9.2 短按处理

```c
case OT_EVENT_KEYMNG_SHORT_CLICK:
    MLOGI("OT_EVENT_KEYMNG_SHORT_CLICK\n");

    switch (event->arg1) {
        case OT_KEY_IDX_1:
        {
            ret = PDT_UI_AlarmPageCheckStorage(TD_FALSE);
            OT_APPCOMM_LOG_AND_RETURN_IF_FAIL(
                ret, TD_FAILURE,
                "SD state is not normal");

            message.what = workModeState.isRunning ?
                OT_EVENT_STATEMNG_STOP :
                OT_EVENT_STATEMNG_START;

            message.arg1 = TD_TRUE;
            message.arg2 = workModeState.workMode;

            ret = SS_PDT_STATEMNG_SendMessage(&message);
            if (ret != TD_SUCCESS) {
                MLOGE("SS_PDT_STATEMNG_SendMessage failed\n");
                return TD_FAILURE;
            }
            break;
        }

        case OT_KEY_IDX_0:
            if (workModeState.workMode ==
                OT_PARAM_WORKMODE_NORM_REC) {
                ret = PDT_UI_TakePhoto();
                OT_APPCOMM_RETURN_IF_FAIL(ret, ret);
            }
            break;
    }

    return TD_SUCCESS;
```

所以：

- `KEY_IDX_0` 短按：在普通录像模式下抓拍；
- `KEY_IDX_1` 短按：根据 `isRunning` 在开始录像和停止录像之间切换。

### 9.3 长按处理

```c
case OT_EVENT_KEYMNG_LONG_CLICK3S:
    MLOGI("OT_EVENT_KEYMNG_LONG_CLICK3S\n");

    switch (event->arg1) {
        case OT_KEY_IDX_1:
#ifdef CONFIG_HC101_A_GB_X10
            /* X10：长按关机 */
            ret = PDT_UI_PowerOff(event, state);
            UI_LOG_AND_RETURN_IF_FAIL(
                ret, TD_FAILURE, "home power off");
#else
            /* 非 X10 原有逻辑：开关 Wi-Fi */
            /* 具体代码省略 */
#endif
            break;

        case OT_KEY_IDX_0:
            MLOGI("factory_reset\n");
            PDT_UI_FactoryReset();
            break;
    }

    return TD_SUCCESS;
```

所以 X10 中：

- `KEY_IDX_0` 长按：恢复出厂设置；
- `KEY_IDX_1` 长按：执行关机。

---

## 10. HC101 X10 按键映射汇总

| 物理 GPIO | HAL 按键索引 | 逻辑事件 ID | 短按功能 | 长按功能 |
|---|---|---|---|---|
| GPIO0_0 | `OT_KEY_IDX_0` | 0 | 抓拍照片 | 恢复出厂设置 |
| GPIO0_7 | `OT_KEY_IDX_1` | 1 | 开始/停止录像 | 关机 |

需要注意，`event.arg1` 传递的是配置中的 `key_id`：

```c
event.arg1 = clickInfo->attr.id;
```

X10 当前刚好配置成：

```text
物理 idx 0 → key_id 0
物理 idx 1 → key_id 1
```

因此 UI 中可以直接用 `OT_KEY_IDX_0/1` 判断。若以后修改 `key_id`，但 UI 判断没有同步修改，就可能出现物理按键与业务功能错位。

---

## 11. 一次短按录像键的完整时序

以 GPIO0_7 短按为例：

```text
1. 用户按下 GPIO0_7
2. KEY_CHECK 线程下一次轮询进入 KEYMNG_ClickCheck(idx=1)
3. SS_HAL_KEY_GetState(1) 查到该按键对应 GPIO0_7
4. HAL_KEY_GetGpioState() 调用 HAL_GPIO_SetDir(0, 7, READ)
5. HAL_GPIO_SetDir() 执行 ioctl(GPIO_SET_DIR)
6. 内核 gpio_ioctl() 调用 ss_gpio_set_dir()
7. HAL_KEY_GetGpioState() 调用 HAL_GPIO_GetBitVal(0, 7)
8. HAL_GPIO_GetBitVal() 执行 ioctl(GPIO_READ_BIT)
9. 内核 gpio_ioctl() 调用 ss_gpio_read_bit()
10. 驱动读取 GPIO0 数据寄存器的 bit7
11. HAL 对 bit7 电平进行反相
12. SS_HAL_KEY_GetState() 返回 OT_KEY_STATE_DOWN
13. KEYMNG 令 keyDownCnt 加一
14. 用户松开按键
15. 后续轮询读到 OT_KEY_STATE_UP
16. 因按下时间少于约 2 秒，发布 OT_EVENT_KEYMNG_SHORT_CLICK
17. event.arg1 = 1
18. UIEvent 订阅者收到事件
19. PDT_UI_ProcStateMsgCallback() 查到 PDT_UI_ProcKeyEvents()
20. PDT_UI_ProcKeyEvents() 进入 KEY_IDX_1 短按分支
21. 根据 workModeState.isRunning 发送 START 或 STOP 消息
22. 状态机真正执行开始录像或停止录像
```

---

## 12. 调试时可以观察的日志

按键初始化成功：

```text
key available: ... keyCnt:2
```

未完成产测导致按键1被屏蔽：

```text
未产测，屏蔽按键1
```

短按事件：

```text
short click event[0]
short click event[1]
OT_EVENT_KEYMNG_SHORT_CLICK
```

长按事件：

```text
long click 3s event[0]
long click 3s event[1]
OT_EVENT_KEYMNG_LONG_CLICK3S
```

APP 连接导致按键被屏蔽：

```text
app is connect return
```

停车模式导致按键被屏蔽：

```text
acc off or parking :..., return
```

GPIO 驱动或 HAL 失败：

```text
open gpiodev failed
gpio set dir failed
gpio read bit failed
SS_HAL_KEY_Init Failed
```

---

## 13. 当前实现需要特别留意的地方

### 13.1 轮询带来的延迟

轮询周期为 200 ms，因此按键状态识别存在最多约一个轮询周期的延迟。特别短的按压也可能落在两次轮询之间而被漏检。

### 13.2 `LONG_CLICK3S` 名称与实际阈值不一致

代码发布的是 `OT_EVENT_KEYMNG_LONG_CLICK3S`，但当前硬编码判断和 X10 配置都是 2000 ms。调试时应以代码实际阈值为准。

### 13.3 长按事件在松开时才发出

当前逻辑是在检测到 `DOWN → UP` 后，根据累计次数判断长按。因此用户一直按住不松手时，UI 不会立刻收到长按事件。

### 13.4 GPIO0_7 有单独反相逻辑

反相条件只判断 `gpioCfg->bit == 7`，没有同时判断 GPIO 组号。以后若增加其他组的 bit7 按键，也会被同样反相，应注意这一隐含条件。

### 13.5 未产测时按键1被屏蔽

`KEYMNG_ClickCheck()` 在产测未完成时直接忽略 `OT_KEY_IDX_1`。此时即使 GPIO 电平和驱动读取都正常，也不会产生录像键事件。

### 13.6 APP 连接时按键业务会被应用层屏蔽

APP 连接状态下，除 X10 的按键1长按关机外，其他按键事件在 `PDT_UI_ProcKeyEvents()` 中直接返回。因此调试实体按键时必须区分：

```text
GPIO 没读到
KEYMNG 没发布事件
UI 收到事件但因 APP 已连接而主动忽略
```

这三种情况表现相似，但所属层级完全不同。

---

## 14. 分层定位故障的方法

| 现象 | 优先检查位置 |
|---|---|
| `/dev/ot_gpio` 不存在 | GPIO 驱动是否加载、`misc_register()` 是否成功 |
| `open gpiodev failed` | `/dev/ot_gpio` 节点和权限 |
| `gpio read bit failed` | ioctl、组号/位号、驱动寄存器映射 |
| GPIO 电平正常但无 `short click event` | KEY_CHECK 线程、产测屏蔽、轮询与消抖 |
| 有 `short click event` 但功能不执行 | EventHub 订阅、UI 事件映射、APP 连接屏蔽 |
| 按键功能互换 | `key_id` 与 UI 的 `event.arg1` 映射 |
| GPIO0_7 状态相反 | bit7 特殊反相代码 |
| 长按时间与名称不符 | 200 ms 轮询、2000 ms 阈值与 `LONG_CLICK3S` 命名不一致 |

---

## 15. 关键源文件索引

| 层级 | 文件 |
|---|---|
| GPIO ioctl 定义 | `source/camera/driver/gpio/ss_gpio.h` |
| GPIO 内核驱动 | `source/camera/driver/gpio/ss_gpio.c` |
| CV610 GPIO 基地址 | `source/camera/driver/gpio/gpio_grpinfo_hi3516cv610.h` |
| 通用 GPIO HAL | `source/camera/hal/common/src/hal_gpio.c` |
| 按键 HAL | `source/camera/hal/key/src/ss_hal_key.c` |
| 按键 HAL 类型定义 | `source/camera/hal/key/include/ss_hal_key.h` |
| HC101 板级按键注册 | `source/camera/demo/dronecam/modules/init/smp/src/board/hi3516cv610_demb.c` |
| X10 按键配置 | `source/camera/demo/dronecam/modules/param/inicfg/hi3516cv610/nonescreen/gc4653_ahd_128M_X10/config_product_devmng.ini` |
| INI 参数加载 | `source/camera/demo/dronecam/modules/param/ini2bin/src/product_iniparam_devmng.c` |
| 应用启动按键管理 | `source/camera/demo/dronecam/modules/init/smp/src/ss_product_main.c` |
| KEYMNG 轮询与事件发布 | `source/camera/component/devmng/src/ss_keymng.c` |
| 按键事件定义 | `source/camera/component/devmng/include/ss_keymng.h` |
| UI EventHub 订阅 | `source/camera/demo/dronecam/modules/ui/modules/ui_event_dispatch.c` |
| UI 按键业务处理 | `source/camera/demo/dronecam/modules/ui/nonescreen/src/ss_product_ui.c` |

## 16. 最简调用栈

```c
/* 应用业务层 */
PDT_UI_ProcKeyEvents()

/* UI/EventHub */
PDT_UI_ProcStateMsgCallback()
PDT_UI_EventDispatchOnEvent()
SS_EVTHUB_Publish()

/* 按键管理层 */
KEYMNG_ClickCheck()
SS_HAL_KEY_GetState()

/* 按键 HAL */
HAL_KEY_GetGpioState()

/* 通用 GPIO HAL */
HAL_GPIO_SetDir()
HAL_GPIO_GetBitVal()

/* 系统调用 */
ioctl(fd, GPIO_SET_DIR, ...)
ioctl(fd, GPIO_READ_BIT, ...)

/* 内核 GPIO 驱动 */
gpio_ioctl()
ss_gpio_set_dir()
ss_gpio_read_bit()

/* 硬件 */
Hi3516CV610 GPIO0 数据寄存器
```

从硬件向应用看，顺序与上面的调用栈相反：驱动读取电平，HAL 转换状态，KEYMNG 生成事件，EventHub 分发，UI 执行业务。
