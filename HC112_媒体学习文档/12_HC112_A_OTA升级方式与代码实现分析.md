# HC112_A OTA 升级方式与代码实现分析

## 1. 文档目的

本文基于 `Z:\HC1XX_SPC020` 工程，对 HC112_A 的 OTA 升级方式、升级包生成、网络传输、升级状态机、镜像拆包、U-Boot 写 Flash 和升级结果处理进行梳理。

本文主要回答以下问题：

1. HC112_A 的 OTA 属于什么升级方式。
2. OTA 升级包如何生成、命名和组织。
3. App 如何通过 Wi-Fi/HTTP 将升级包传给设备。
4. Linux 主程序和 U-Boot 分别负责什么工作。
5. 关键代码的作用和调用关系是什么。
6. 当前实现存在哪些风险，后续应如何改进。

> 说明：本文为代码阅读与流程分析文档，没有修改 OTA 工程代码。

---

## 2. OTA 总体结论

HC112_A 当前使用的是两阶段升级方式：

```text
App/客户端通过设备 Wi-Fi 上传 .appsw 升级包
                    │
                    ▼
Linux 主程序将升级包保存到 SD 卡
                    │
                    ▼
检查型号、CRC、包头包尾和分区大小
                    │
                    ▼
从升级包中拆出 config 和各分区镜像到 SD 卡
                    │
                    ▼
重启设备
                    │
                    ▼
U-Boot 从 SD 卡读取 config 和镜像文件
                    │
                    ▼
擦除并写入 SPI NOR Flash
                    │
                    ▼
启动新固件，Linux 清理 SD 卡上的临时升级文件
```

因此，该方案具有以下特点：

- OTA 的传输通道是设备 Wi-Fi 上的 HTTP/CGI。
- SD 卡是升级包和拆包镜像的中转存储空间。
- Linux 主要负责接收、校验、拆包和重启。
- 真正擦除、写入 SPI NOR 的工作主要由 U-Boot 完成。
- 当前不是 A/B 双系统升级，没有备用系统分区。
- 当前没有数字签名校验，主要依靠 CRC32 和 MD5 检测数据损坏。

---

## 3. 关键代码文件

| 功能 | 文件 |
| --- | --- |
| OTA 功能配置 | `Z:\HC1XX_SPC020\config.conf` |
| 升级包结构定义 | `source/camera/component/upgrade/include/ot_upgrade_define.h` |
| 升级模块接口 | `source/camera/component/upgrade/include/ss_upgrade.h` |
| 升级包校验、拆包和状态管理 | `source/camera/component/upgrade/src/ss_upgrade.c` |
| Linux Flash 分区读写接口 | `source/camera/component/upgrade/src/upgrade_partition.c` |
| 升级包生成工具 | `source/camera/tools/upgrade_generate/src/ss_upgrade_generate_main.c` |
| OTA CGI 接口和文件接收 | `source/camera/demo/dronecam/modules/netctrl/src/cgi/product_netctrl_upgrade_cgi.c` |
| CGI 命令注册 | `source/camera/demo/dronecam/modules/netctrl/src/cgi/product_netctrl_register_cmd.c` |
| SD 卡升级包检测 | `source/camera/demo/dronecam/modules/statemng/src/workstate/product_statemng_msgproc_base.c` |
| 升级状态机 | `source/camera/demo/dronecam/modules/statemng/src/workstate/product_statemng_state_upgrade.c` |
| 升级前资源释放、启动升级 | `source/camera/demo/dronecam/modules/statemng/src/workstate/product_statemng_msgproc_upgrade.c` |
| 无屏 UI 升级事件处理 | `source/camera/demo/dronecam/modules/ui/nonescreen/src/ss_product_ui.c` |
| 升级包生成规则 | `source/camera/demo/dronecam/rootfs/Makefile` |
| U-Boot SD 卡自动升级 | `platform/sdk/open_source/u-boot/u-boot-2022.07/product/update/auto_update_adaptation.c` |
| U-Boot 自动升级入口 | `platform/sdk/open_source/u-boot/u-boot-2022.07/board/vendor/hi3516cv610/hi3516cv610.c` |

---

## 4. OTA 功能如何打开

工程根目录 `config.conf` 中包含：

```text
CONFIG_UPGRADE_SUPPORT=y
```

该配置使以下模块参与编译：

- `SS_UPGRADE_Init()` 升级模块初始化。
- OTA 事件注册。
- CGI 升级接口。
- 升级状态机。
- `.sw` 和 `.appsw` 升级包生成。

U-Boot 当前配置还包含：

```text
CONFIG_AUTO_UPDATE=y
CONFIG_AUTO_SD_UPDATE=y
CONFIG_AUTO_SD_UPDATE_IS_IN_SDIO0=y
```

含义分别为：

- `CONFIG_AUTO_UPDATE=y`：打开 U-Boot 自动升级功能。
- `CONFIG_AUTO_SD_UPDATE=y`：允许 U-Boot 从 SD 卡查找升级文件。
- `CONFIG_AUTO_SD_UPDATE_IS_IN_SDIO0=y`：升级 SD 卡连接在 SDIO0。

---

## 5. 升级包生成方式

### 5.1 Makefile 调用

文件：`source/camera/demo/dronecam/rootfs/Makefile`

关键代码：

```make
upgrade_pkt:
	@rm -f $(PDT_OUT_BURN)/*.appsw
	@cp $(PDT_ELF_X86_PATH)/$(UPGRADE_TOOL_NAME) $(PDT_OUT_BURN)/
	@cd $(PDT_OUT_BURN)/;chmod +x ./$(UPGRADE_TOOL_NAME);./$(UPGRADE_TOOL_NAME) 0 $(DEVICE_MODEL) $(BUILD_SOFTVERSION) config
	@cd $(PDT_OUT_BURN)/;./$(UPGRADE_TOOL_NAME) 1 $(DEVICE_MODEL) $(BUILD_SOFTVERSION) config
	@rm -f $(PDT_OUT_BURN)/$(UPGRADE_TOOL_NAME)
```

代码含义：

1. 删除输出目录中旧的 `.appsw` 文件，避免混入旧升级包。
2. 将主机端升级包生成工具复制到烧录输出目录。
3. 参数 `0` 生成 U-Boot 类型的 `.sw` 包。
4. 参数 `1` 生成 App OTA 使用的 `.appsw` 包。
5. 参数中同时传入设备型号、软件版本和 `config` 分区配置文件。
6. 生成完成后删除临时生成工具。

### 5.2 两种包类型

文件：`source/camera/component/upgrade/include/ot_upgrade_define.h`

```c
enum {
    UPGRADE_IMAGES_BY_UBOOT = 0,
    UPGRADE_IMAGES_BY_APP
};
```

含义：

- `UPGRADE_IMAGES_BY_UBOOT`：包类型值为 0，设计用途是由 U-Boot 完成分区写入。
- `UPGRADE_IMAGES_BY_APP`：包类型值为 1，设计用途是由 Linux App 完成分区写入。

但在 HC112_A 当前代码中，Linux 直接写分区的调用被关闭，因此两类包最终都依赖 SD 卡和 U-Boot 完成实际 Flash 更新。

### 5.3 升级包命名

升级包生成工具中的代码：

```c
if (pktType == UPGRADE_IMAGES_BY_UBOOT) {
    snprintf(szReleasePacketName, sizeof(szReleasePacketName),
             "./upgrade_%s_%s.sw", szModel, szSoftVersion);
} else {
    snprintf(szReleasePacketName, sizeof(szReleasePacketName),
             "./upgrade_HC112_%s.appsw", szSoftVersion);
}
```

生成 `.appsw` 后，程序继续计算整个升级包的 MD5：

```c
snprintf(cmd, sizeof(cmd), "md5sum %s | awk '{print $1}'", szReleasePacketName);
SS_UPGRADE_Getcmdresult(cmd, md5_1, sizeof(md5_1));

snprintf(szReleasePacketNameMd5, sizeof(szReleasePacketNameMd5),
         "./upgrade_HC112_%s_%s.appsw", md5_1, szSoftVersion);
rename(szReleasePacketName, szReleasePacketNameMd5);
```

最终文件名形式为：

```text
upgrade_HC112_<文件MD5>_<软件版本>.appsw
```

示例：

```text
upgrade_HC112_dfbd49bf973c68f19e83d648f9909ad1_1.0.0.0.20260729.appsw
```

文件名中加入 MD5 的目的，是让设备扫描 SD 卡升级包时可以再次计算文件 MD5，并与文件名中的 MD5 比较。

---

## 6. 升级包内部结构

升级包结构定义在 `ot_upgrade_define.h`。

### 6.1 包头结构

```c
typedef struct UPGRADE_PKT_HEAD_S
{
    td_u32 u32Magic;
    td_u32 u32Crc;
    td_u32 u32HeadVer;
    td_u32 u32PktLen;
    td_u8  compress;
    td_u8  pktType;
    td_u8  reserved0;
    td_u8  reserved1;
    td_char szPktModel[OT_APPCOMM_COMM_STR_LEN];
    td_char szPktSoftVersion[OT_APPCOMM_COMM_STR_LEN];
    td_char szBootArgs[OT_UPGRADE_MAX_ENV_LEN];
    td_char szBootCmd[OT_UPGRADE_MAX_ENV_LEN];
    td_u32 u32ConfigFileOffSet;
    td_s32 s32PartitionCnt;
    td_u32 au32PartitionOffSet[OT_UPGRADE_MAX_PART_CNT];
} OT_UPGRADE_PKT_HEAD_S;
```

字段解释：

| 字段 | 作用 |
| --- | --- |
| `u32Magic` | 包头魔数，用于判断文件是否为合法升级包 |
| `u32Crc` | 从包头版本字段到镜像数据结束位置的 CRC32 |
| `u32HeadVer` | 升级包头结构版本 |
| `u32PktLen` | 整个升级包总长度 |
| `compress` | 镜像是否压缩，当前生成代码设置为不压缩 |
| `pktType` | 0 表示 U-Boot 类型，1 表示 App 类型 |
| `szPktModel` | 升级包适用的设备型号 |
| `szPktSoftVersion` | 升级包的软件版本 |
| `szBootArgs` | 新固件的 Linux 启动参数和 Flash 分区布局 |
| `szBootCmd` | 新固件的 U-Boot 启动命令 |
| `u32ConfigFileOffSet` | `config` 文件在升级包中的偏移 |
| `s32PartitionCnt` | 升级包包含的分区镜像数量 |
| `au32PartitionOffSet[]` | 每个分区头在升级包中的偏移 |

### 6.2 分区头结构

```c
typedef struct UPGRADE_PARTITION_HEAD_S
{
    td_char szPartName[OT_UPGRADE_PARTITION_NAME_MAX_LEN];
    td_u32 upgradeMode;
    td_u32 partDataOffset;
    td_u32 u32OriDataLen;
    td_u32 u32DataLen;
} OT_UPGRADE_PARTITION_HEAD_S;
```

字段解释：

- `szPartName`：镜像文件名或目标分区名，例如 `uImage`、`rootfs.squashfs`。
- `u32OriDataLen`：镜像原始长度。
- `u32DataLen`：镜像在升级包中实际保存的长度。
- `upgradeMode`、`partDataOffset`：预留给不同升级方式使用。

### 6.3 包尾结构

```c
typedef struct UPGRADE_PKT_TAIL_S
{
    td_u32 u32Magic;
} OT_UPGRADE_PKT_TAIL_S;
```

包尾魔数用于检查升级包是否完整结束。当前使用：

```c
#define OT_UPGRADE_PACKET_HEAD_MAGIC 0x08122515
#define OT_UPGRADE_PACKET_TAIL_MAGIC 0x0812251d
```

---

## 7. App OTA 网络传输流程

### 7.1 CGI 命令注册

文件：`product_netctrl_register_cmd.c`

```c
{ "checkupgradeinfo.cgi", "checkupgradeinfo&", OT_CGI_METHOD_GET,
  PDT_NETCTRL_UpgradeCgi },

{ "cancelupgrade.cgi", "cancelupgrade&", OT_CGI_METHOD_GET,
  PDT_NETCTRL_CancelUpgradeCgi },
```

含义：

- `checkupgradeinfo.cgi`：准备 OTA，检查参数并进入升级模式。
- `cancelupgrade.cgi`：取消正在进行的 OTA 上传。

### 7.2 OTA 准备参数

文件：`product_netctrl_upgrade_cgi.c`

```c
OT_HISNET_ArgOpt opts[] = {
    NETCTRL_ARG_OPT("model", ARG_TYPE_MUST | ARG_TYPE_STRING,
                    TD_NULL, pktInfo.modelDsc, sizeof(pktInfo.modelDsc)),
    NETCTRL_ARG_OPT("softversion", ARG_TYPE_MUST | ARG_TYPE_STRING,
                    TD_NULL, pktInfo.softVerDsc, sizeof(pktInfo.softVerDsc)),
    NETCTRL_ARG_OPT("pktlen", ARG_TYPE_MUST | ARG_TYPE_INT,
                    TD_NULL, &pktInfo.pktLen, sizeof(pktInfo.pktLen)),
};
```

客户端必须提供：

- `model`：升级包设备型号。
- `softversion`：升级包版本。
- `pktlen`：完整升级包长度。

### 7.3 检查 SD 卡空间

```c
ret = SS_STORAGEMNG_GetFsInfo(storageCfg.mntPath, &fsInfo);

if (fsInfo.u64AvailableSize <= pktInfo->pktLen) {
    responseCgi(returnContent,
                "SvrFuncResult=\"%d\"\r\n",
                OT_NETCTRL_SD_SPACE_NOT_ENOUGH);
    return OT_NETCTRL_SD_SPACE_NOT_ENOUGH;
}
```

含义：

1. 获取 SD 卡文件系统信息。
2. 判断剩余空间是否大于升级包长度。
3. 空间不足时直接拒绝 OTA。

由此可以确认：当前网络 OTA 依赖 SD 卡，未插卡或卡空间不足时无法完成升级。

### 7.4 停止录像并切换升级模式

```c
if ((workModeState->workMode == OT_PARAM_WORKMODE_NORM_REC) &&
    (workModeState->isRunning == TD_TRUE)) {
    message.what = OT_EVENT_STATEMNG_STOP;
    PDT_NETCTRL_SendSyncMsg(&message, &result);
}

message.what = OT_EVENT_STATEMNG_SWITCH_WORKMODE;
message.arg2 = OT_PARAM_WORKMODE_UPGRADE;
PDT_NETCTRL_SendSyncMsg(&message, &result);
```

含义：

1. 如果当前处于正常录像模式并且正在录像，先停止录像。
2. 将整个产品状态机切换到升级模式。
3. 避免录像持续占用 SD 卡、内存和媒体线程，影响 OTA 文件接收。

### 7.5 注册上传回调

```c
OT_THTTPD_FileFunc fileOptFunc = { 0 };
fileOptFunc.fopen  = PDT_NETCTRL_OpenUpgradePkt;
fileOptFunc.fwrite = PDT_NETCTRL_UpgradeReceivePkt;
fileOptFunc.fclose = PDT_NETCTRL_UpgradeClosePkt;
SS_THTTPD_RegisterUploadFileProc(fileOptFunc);
```

含义：

- HTTP 服务收到文件时，不使用默认文件处理，而是调用产品 OTA 的打开、写入和关闭函数。
- OTA 模块通过这些回调维护上传偏移和进度。

### 7.6 分块传输和断点续传

```c
#define PDT_UPGRADE_UNITSIZE (256 * 1024)
```

每个 OTA 传输单元默认 256 KiB。

```c
if (g_upgradeCtx.offset == 0) {
    fp = fopen(g_upgradeCtx.pktPath, "w");
} else {
    fp = fopen(g_upgradeCtx.pktPath, "r+");
}

fseek(filefp, g_upgradeCtx.offset, SEEK_SET);
```

含义：

- 第一次接收时以 `w` 模式创建升级文件。
- 已经接收过部分数据时以 `r+` 模式重新打开。
- 使用 `offset` 定位到上次完成位置后继续写入。

收到数据后：

```c
saveLen = PDT_NETCTRL_UpgradeWriten(recvBuf, bufLen, fp);
g_upgradeCtx.offset += bufLen;
g_upgradeCtx.recvBufLen += bufLen;

event.EventID = OT_EVENT_NETCTRL_RECEIVE_PKT;
event.arg1 = g_upgradeCtx.offset * 100U / g_upgradeCtx.pktLen;
SS_EVTHUB_Publish(&event);
```

含义：

1. 把网络数据写入 SD 卡临时升级文件。
2. 累计已接收字节数。
3. 根据已接收长度计算上传百分比。
4. 发布上传进度事件。

### 7.7 超时处理

```c
#define PDT_UPGRADE_MAX_WAITCOUNT 15
#define NETCTRL_UPGRADE_TIMEOUT_US (2000 * 1000)
```

每隔 2 秒检查一次 `offset` 是否变化。如果连续 15 次无变化，则认为 OTA 上传超时，时间约为：

```text
2 秒 × 15 次 = 30 秒
```

---

## 8. 升级包校验流程

上传长度达到 `pktLen` 后调用：

```c
SS_UPGRADE_CheckPkt(g_upgradeCtx.pktPath, &upgradeDevInfo);
```

### 8.1 包头魔数检查

```c
if (OT_UPGRADE_PACKET_HEAD_MAGIC != pstPktHead->u32Magic) {
    return OT_UPGRADE_EPKT_INVALID;
}
```

作用：排除普通文件、错误格式文件以及文件头损坏。

### 8.2 型号检查

```c
if (strncmp(pstPktHead->szPktModel,
            pstPktInfo->szModel,
            OT_APPCOMM_COMM_STR_LEN)) {
    return OT_UPGRADE_EPKT_INVALID;
}
```

作用：升级包头中的型号必须和设备当前型号相同，避免错误产品固件互刷。

### 8.3 CRC32 检查

```c
s32Ret = UPGRADE_CheckPktCrc(pstPktHead, s32PktFd,
    pu8PktBuf + sizeof(OT_UPGRADE_PKT_HEAD_S),
    UPGRADE_IMGDATA_BUFF_MAX_SIZE);
```

作用：重新计算包头和镜像数据的 CRC32，与包头记录值比较，检查文件在传输和保存过程中是否损坏。

### 8.4 包尾检查

```c
if (OT_UPGRADE_PACKET_TAIL_MAGIC != stPktTail.u32Magic) {
    return OT_UPGRADE_EPKT_INVALID;
}
```

作用：检查升级包是否接收完整，防止使用被截断的文件升级。

### 8.5 分区大小检查

```c
s32Ret = UPGRADE_CheckFlashSize(pstPktHead);
s32Ret = UPGRADE_CheckALLPartitionsSize(s32PktFd, pstPktHead);
```

作用：

- 检查升级包总镜像大小是否超过 Flash。
- 检查单个镜像是否超过目标分区容量。

校验全部通过后发布：

```c
stEvent.EventID = OT_EVENT_UPGRADE_NEWPKT;
SS_EVTHUB_Publish(&stEvent);
return OT_UPGRADE_PKT_AVAILABLE;
```

---

## 9. 升级状态机流程

### 9.1 启动升级

网络上传完成后发送：

```c
message.what = OT_EVENT_STATEMNG_UPGRADE_START;
PDT_NETCTRL_SendSyncMsg(&message, &result);
```

升级状态机收到该消息后调用：

```c
PDT_STATEMNG_UpgradeStateProcStartUpgradeMsg();
```

### 9.2 升级前释放资源

`PDT_STATEMNG_UpgradePreProcess()` 会释放或停止以下模块：

- LVGL 显示。
- 声控 AI 引擎。
- ACC 管理。
- GPS 管理。
- 按键管理。
- 文件管理。
- 定时任务。
- 视频输入。
- 音频输入输出。
- 参数管理。
- AHD 管理。
- GSensor 管理。

例如：

```c
ret = HYT_PDT_Deinit_Media_aiengine();
ret = SS_ACCMNG_Deinit();
ret = SS_GPSMNG_Stop();
ret = SS_KEYMNG_Deinit();
(td_void)SS_FILEMNG_Deinit();
(td_void)SS_MEDIA_DeinitVideoIn();
(td_void)SS_MEDIA_DeinitAudioIn();
ret = SS_PDT_PARAM_Deinit();
```

目的：

1. 停止媒体和外设线程。
2. 释放内存和文件句柄。
3. 避免录像继续访问 SD 卡。
4. 降低升级阶段资源竞争和死机概率。

### 9.3 从事件历史获取升级包路径

```c
ret = SS_EVTHUB_GetEventHistory(OT_EVENT_UPGRADE_NEWPKT,
                                &upgradeEvent);
eventInfo = (OT_UPGRADE_EVENT_INFO_S *)upgradeEvent.aszPayload;
```

`OT_EVENT_UPGRADE_NEWPKT` 的负载中保存：

- 升级包路径。
- 升级包版本。
- 升级包长度。

状态机最多重试 10 次读取该事件，每次间隔 100 ms。

### 9.4 调用升级模块

```c
ret = SS_UPGRADE_DoUpgrade(storageMngCfg.mntPath,
                           eventInfo->szPktFilePath);
```

第一个参数是 SD 卡挂载目录，第二个参数是完整升级包文件路径。

---

## 10. Linux 拆包流程

`SS_UPGRADE_DoUpgrade()` 的主要工作如下：

```c
ret = UPGRADE_ReadPktHead(pktFd, &pktHead);
ret = UPGRADE_CheckFlashSize(&pktHead);

if (pktHead.pktType == UPGRADE_IMAGES_BY_UBOOT ||
    pktHead.pktType == UPGRADE_IMAGES_BY_APP) {
    ret = UPGRADE_DoUpgradeByAPP(pktHead.pktType,
                                 pktFd,
                                 pktBuf,
                                 &pktHead,
                                 pszPktPath);
}
```

### 10.1 拆出 config 文件

```c
ret = UPGRADE_SeparatePartitionImage(
    pktPath,
    pktFd,
    pktHead->u32ConfigFileOffSet + sizeof(OT_UPGRADE_PARTITION_HEAD_S),
    &partitionHead,
    imgDataBuf,
    UPGRADE_IMGDATA_BUFF_MAX_SIZE);
```

作用：根据包头记录的偏移，从升级包中取出 `config` 文件并保存到 SD 卡根目录。

### 10.2 拆出全部分区镜像

```c
for (i = 0; i < pktHead->s32PartitionCnt; ++i) {
    UPGRADE_ReadPartitionHead(pktFd,
        pktHead->au32PartitionOffSet[i],
        &partitionHead);

    UPGRADE_SeparatePartitionImage(
        pktPath,
        pktFd,
        pktHead->au32PartitionOffSet[i] +
            sizeof(OT_UPGRADE_PARTITION_HEAD_S),
        &partitionHead,
        imgDataBuf,
        UPGRADE_IMGDATA_BUFF_MAX_SIZE);
}
```

拆包后 SD 卡上可能出现：

```text
/app/sd/config
/app/sd/u-boot.bin
/app/sd/rawparam
/app/sd/rawparambak
/app/sd/resImage
/app/sd/uImage
/app/sd/rootfs.squashfs
/app/sd/appfs.jffs2
```

### 10.3 为什么 Linux 没有直接写 Flash

代码中保留了直接写 Flash 的函数：

```c
UPGRADE_WritePartitionByName(pktPath, partitionHead.szPartName);
```

但是当前调用位于：

```c
#if 0
ret = UPGRADE_WritePartitionByName(pktPath,
                                   partitionHead.szPartName);
#endif
```

因此这段代码不会参与编译，Linux 阶段只检查镜像大小和拆出文件，不执行真正的 Flash 擦写。

拆包成功后：

```c
UPGRADE_WriteStatus(UPGRADE_STATUS_FINISH);
SS_SYSTEM_Reboot();
```

设备随后重启进入 U-Boot 自动升级阶段。

---

## 11. U-Boot 写 Flash 流程

### 11.1 U-Boot 自动升级入口

文件：`board/vendor/hi3516cv610/hi3516cv610.c`

```c
if (is_auto_update())
    auto_update_flag = 1;
else
    auto_update_flag = 0;

if (auto_update_flag)
    do_auto_update();
```

设计含义：

1. 判断是否打开自动升级功能。
2. 如果允许自动升级，则调用 `do_auto_update()`。

### 11.2 查找 SD 卡和 config

文件：`product/update/auto_update_adaptation.c`

```c
#define AU_CONFIG "config"
```

```c
stor_dev = detect_external_storage(j);
fat_register_device(stor_dev, 1);
file_fat_detectfs();
get_env_from_config();
bootargs_analyze();
update_to_flash();
```

代码含义：

1. 初始化并检测外部 SD 卡。
2. 使用 SD 卡的第一个 FAT 分区。
3. 检查 FAT 文件系统。
4. 读取 SD 卡根目录中的 `config`。
5. 解析 `config` 内的 `bootargs` 和分区表。
6. 查找与分区名称对应的镜像文件。
7. 调用 Flash 擦除和写入接口更新设备。

### 11.3 SPI NOR 写入

```c
spinor_flash = spi_flash_probe(0, 0, 0, 0);
```

作用：初始化 SPI NOR Flash。

擦除过程：

```c
ret = spi_flash_erase(flash, offset, erase_step);
```

写入过程：

```c
ret = flash->write(flash, offset, write_step, pbuf);
```

代码按照 Flash 擦除块大小循环处理，并调用：

```c
schedule_notify(offset, write_len, write_start);
```

输出升级百分比，同时控制红绿 LED 显示升级进度。

---

## 12. SD 卡本地升级流程

HC112_A 除 App OTA 外，还支持直接把升级包放入 SD 卡。

SD 卡挂载完成后调用：

```c
PDT_STATEMNG_IsNewUpgradePktExist();
```

函数内部：

```c
SS_UPGRADE_Init();
PDT_STATEMNG_GetUpgradeDevInfo(&upgradeDevInfo);
SS_PDT_PARAM_GetStorageCfg(&storageCfg);
SS_UPGRADE_SrchNewPkt(storageCfg.mntPath, &upgradeDevInfo);
```

`SS_UPGRADE_SrchNewPkt()` 遍历 SD 卡目录：

```c
if (UPGRADE_CheckPktNameValid(pstDirItem->d_name)) {
    UPGRADE_CheckPktValid(&stPktInfo);
}
```

当前文件名检查只判断是否以 `upgrade` 开头：

```c
ret = strncmp(pszPktName,
              OT_UPGRADE_PKT_PREFIX,
              sizeof(OT_UPGRADE_PKT_PREFIX) - 1);
```

找到合法包后，还会执行：

```c
snprintf(cmd, sizeof(cmd),
         "md5sum %s | awk '{print $1}'",
         stPktInfo.szPktFilePath);

if (strcmp(appsw_md5sum, stPktInfo.szFileMd5sum) == 0) {
    bFound = TD_TRUE;
}
```

也就是把实际文件 MD5 与文件名中的 MD5 进行比较。

校验成功后发布 `OT_EVENT_UPGRADE_NEWPKT`。无屏 UI 收到事件后直接调用升级处理函数：

```c
if (PDT_STATEMNG_GetNewUpgradePktValue()) {
    PDT_STATEMNG_UpgradeStateProcStartUpgradeMsg();
}
```

后续流程与 App OTA 相同：拆包、重启、U-Boot 写 Flash。

---

## 13. 升级状态记录和启动后处理

升级状态包括：

```c
typedef enum {
    UPGRADE_STATUS_IDLE = 0,
    UPGRADE_STATUS_PROCESSING,
    UPGRADE_STATUS_FINISH,
    UPGRADE_STATUS_BUTT
} UPGRADE_STATUS_E;
```

含义：

- `IDLE`：没有升级任务。
- `PROCESSING`：升级已经开始但尚未完成。
- `FINISH`：升级流程已经完成。

设备启动时 `SS_UPGRADE_Init()` 读取升级状态：

```c
if (UPGRADE_STATUS_PROCESSING == s_stUPGRADECtx.enStatus) {
    stEvent.EventID = OT_EVENT_UPGRADE_FAILURE;
} else if (UPGRADE_STATUS_FINISH == s_stUPGRADECtx.enStatus) {
    stEvent.EventID = OT_EVENT_UPGRADE_SUCCESS;
}
```

设计目的：

- 如果上次停留在 `PROCESSING`，说明升级中途异常断电或程序崩溃，报告失败。
- 如果上次记录为 `FINISH`，报告升级成功。

主程序正常启动后还会删除 SD 卡上的拆包文件：

```c
if (access("/app/sd/nodelete.txt", F_OK) != 0) {
    SS_System("rm -rf /app/sd/*.squashfs /app/sd/*.jffs2 "
              "/app/sd/*.ubifs /app/sd/main_app /app/sd/config "
              "/app/sd/rawparam /app/sd/rawparambak /app/sd/resImage "
              "/app/sd/u-boot.bin /app/sd/uImage");
}
```

如果 SD 卡中存在：

```text
/app/sd/nodelete.txt
```

则不会自动删除这些文件，方便调试和重复观察升级过程。

---

## 14. 完整调用链

### 14.1 App OTA 调用链

```text
App 选择 .appsw 文件
  ↓
checkupgradeinfo.cgi
  ↓
PDT_NETCTRL_UpgradeCgi()
  ↓
PDT_NETCTRL_UpgradePrepare()
  ├─ 检查型号和版本参数
  ├─ 检查 SD 卡空间
  └─ 注册 HTTP 文件上传回调
  ↓
PDT_NETCTRL_EnterUpgradeMode()
  ├─ 停止录像
  └─ 切换 OT_PARAM_WORKMODE_UPGRADE
  ↓
PDT_NETCTRL_OpenUpgradePkt()
PDT_NETCTRL_UpgradeReceivePkt()
PDT_NETCTRL_UpgradeClosePkt()
  ↓
升级包完整接收
  ↓
PDT_NETCTRL_StartUpgrade()
  ↓
SS_UPGRADE_CheckPkt()
  ├─ 包头魔数
  ├─ 型号
  ├─ CRC32
  ├─ 包尾魔数
  └─ Flash/分区大小
  ↓
发布 OT_EVENT_UPGRADE_NEWPKT
  ↓
发送 OT_EVENT_STATEMNG_UPGRADE_START
  ↓
PDT_STATEMNG_UpgradeStateProcStartUpgradeMsg()
  ↓
PDT_STATEMNG_UpgradePreProcess()
  ↓
SS_UPGRADE_DoUpgrade()
  ↓
拆出 config 和分区镜像到 SD 卡
  ↓
SS_SYSTEM_Reboot()
  ↓
U-Boot do_auto_update()
  ↓
读取 config，解析分区
  ↓
擦除并写入 SPI NOR
  ↓
启动新固件
```

### 14.2 SD 卡升级调用链

```text
SD 卡插入或开机挂载
  ↓
PDT_STATEMNG_BaseStateProcMountedMsg()
  ↓
PDT_STATEMNG_IsNewUpgradePktExist()
  ↓
SS_UPGRADE_SrchNewPkt()
  ├─ 查找 upgrade* 文件
  ├─ 校验包结构
  ├─ 比较型号
  ├─ 检查 CRC
  └─ 检查文件名 MD5
  ↓
发布 OT_EVENT_UPGRADE_NEWPKT
  ↓
PDT_UI_ProcUpgradeNewPktEvent()
  ↓
PDT_STATEMNG_UpgradeStateProcStartUpgradeMsg()
  ↓
拆包、重启、U-Boot 写 Flash
```

---

## 15. 当前代码存在的问题和风险

### 15.1 版本比较没有真正限制版本

当前代码：

```c
static td_s32 UPGRADE_CompareVersion(const td_char *ver1,
                                     const td_char *ver2)
{
    td_s32 ret = strncmp(ver1, ver2, OT_APPCOMM_COMM_STR_LEN);

    if (ret == 0) {
        return 1;
    } else if (ret < 0) {
        return 1;
    } else {
        return 1;
    }
}
```

无论版本相同、较旧还是较新，都会返回 `1`。

结果：

- 可以重复升级相同版本。
- 可以降级旧版本。
- 没有防回滚能力。

建议：将版本解析为确定的数字字段，例如主版本、次版本、日期和修订号，再逐项比较。

### 15.2 没有数字签名

当前完整性校验主要是：

- CRC32。
- 文件名 MD5。

它们能够发现文件损坏，但不能证明升级包由公司官方生成。攻击者重新制作包后也可以重新计算 CRC 和 MD5。

建议：增加 RSA-2048、ECDSA 或 Ed25519 数字签名，并将公钥固化在 Bootloader 或只读分区。

### 15.3 网络 OTA 没有执行文件名 MD5 校验

`SS_UPGRADE_SrchNewPkt()` 扫描 SD 卡时会执行 MD5 校验，但网络上传完成后的 `SS_UPGRADE_CheckPkt()` 主要执行包内 CRC 校验。

建议：网络 OTA 上传结束后同样计算整个 `.appsw` 文件 MD5，并与文件名或服务器下发值比较。

### 15.4 不支持 A/B 系统回退

当前升级直接覆盖现有分区。写 Flash 过程中断电可能导致：

- U-Boot 损坏。
- Kernel 损坏。
- rootfs 无法挂载。
- appfs 不完整。

建议：

1. 最少避免 OTA 更新 U-Boot，除非必须。
2. 如果 Flash 空间允许，引入 A/B 系统分区。
3. 新系统启动成功后再写入启动成功标志。
4. 启动失败超过次数后自动切回旧分区。

### 15.5 Linux 记录完成状态的时机偏早

当前 Linux 拆包成功后，就执行：

```c
UPGRADE_WriteStatus(UPGRADE_STATUS_FINISH);
```

但此时 U-Boot 还没有真正写 Flash。

因此这个状态更接近“升级包准备完成”，而不是“新固件已经成功写入并启动”。

建议：

- Linux 拆包完成时记录 `READY`。
- U-Boot 写 Flash 完成时记录 `FLASH_DONE`。
- 新固件成功运行并完成自检时记录 `BOOT_OK`。

### 15.6 `is_auto_update()` 缺少返回值

当前代码：

```c
static int is_auto_update(void)
{
#if (CONFIG_AUTO_SD_UPDATE == 1) || (CONFIG_AUTO_USB_UPDATE == 1)
    writel(...);
    writel(...);
#else
    return 0;
#endif
}
```

打开 SD OTA 时，函数执行寄存器配置后没有明确 `return 1;`，但调用者使用：

```c
if (is_auto_update())
```

这是 C 语言未定义行为。不同编译器版本或优化等级下，返回结果可能不一致。

建议修改为：

```c
static int is_auto_update(void)
{
#if (CONFIG_AUTO_SD_UPDATE == 1) || (CONFIG_AUTO_USB_UPDATE == 1)
    /* SDIO pinmux configuration */
    writel(...);
    writel(...);
    return 1;
#else
    return 0;
#endif
}
```

### 15.7 Linux 直接写 Flash 代码与实际流程不一致

工程保留了完整的 Linux Flash 写入函数，但真实调用被 `#if 0` 关闭，容易让维护人员误判升级实现。

建议：

- 如果确定只使用 U-Boot 写入，应增加明确注释。
- 如果以后恢复 Linux 写入，需要重新进行掉电、挂载分区和根文件系统安全验证。

---

## 16. OTA 验证方法

### 16.1 编译输出检查

编译完成后检查输出目录是否包含：

```text
upgrade_<DEVICE_MODEL>_<VERSION>.sw
upgrade_HC112_<MD5>_<VERSION>.appsw
config
uImage
rootfs.squashfs
appfs.jffs2
```

### 16.2 主机端检查 MD5

Linux 编译服务器执行：

```bash
md5sum upgrade_HC112_*.appsw
```

计算结果应与文件名中的 MD5 一致。

### 16.3 设备端确认 OTA 文件

```sh
ls -lh /app/sd/upgrade*
md5sum /app/sd/upgrade*.appsw
```

### 16.4 观察 Linux 阶段日志

重点日志包括：

```text
Receive Upgrade pkt End!
ValidPkt
NewPkt
preprocess begin
preprocess done
start board upgrade
partitionName=
Image FileName
Do Upgrade Success, try to reboot
```

### 16.5 观察 U-Boot 阶段日志

重点日志包括：

```text
mmc storage device found
Operation at ... complete
spinor erase
spinor write
update success
```

### 16.6 升级后检查版本

设备启动后可通过产测串口执行：

```text
factory version
```

同时检查：

```sh
cat /proc/cmdline
```

确认新固件版本、启动参数和分区布局均符合预期。

### 16.7 掉电测试

量产前建议分别在以下阶段做掉电测试：

1. OTA 包上传 20%、50%、90% 时断电。
2. Linux 拆包过程中断电。
3. U-Boot 擦除分区时断电。
4. U-Boot 写 Kernel、rootfs、appfs 时断电。
5. Flash 写完但新系统尚未完全启动时断电。

测试重点是确认设备能否恢复、能否重新升级以及是否会彻底无法启动。

---

## 17. 总结

HC112_A 当前 OTA 的核心设计是：

```text
HTTP 负责传输
SD 卡负责缓存和中转
Linux 负责校验与拆包
U-Boot 负责真正写 Flash
```

该方案实现简单，能够复用 U-Boot 的 SD 卡强制升级能力，并且网络中断时不会立即破坏 Flash。但它依赖 SD 卡、没有数字签名、没有 A/B 回滚，同时存在版本比较失效和 `is_auto_update()` 缺少返回值等问题。

在保持现有架构的情况下，建议优先整改顺序为：

1. 修复 `is_auto_update()` 返回值。
2. 修复版本比较逻辑。
3. 统一网络 OTA 和 SD OTA 的 MD5 校验。
4. 增加升级包数字签名。
5. 调整升级状态写入时机。
6. 根据 Flash 容量评估 A/B 升级和失败回退机制。

