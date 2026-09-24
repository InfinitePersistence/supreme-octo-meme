# HC112 PROC 参数说明、错误定位与 INI 对照

> 适用工程：`Z:\HC1XX_SPC020`，本文简称 HC112。  
> 适用默认配置：Hi3516CV610 + GC8613，3840×2160@25 fps。  
> 本文只做学习和只读分析，不包含任何写 proc、修改 INI 或重启业务的命令。

## 1. 本文怎样使用

每个 proc 节点都从四个角度说明：

1. **字段有什么用**：字段是配置、状态还是累计计数；
2. **正常时怎么看**：HC112 默认4K25下应看到什么；
3. **错误去哪里找**：具体检查哪张表、哪一列；
4. **是否对应 INI**：能直接对应、经过代码转换后对应，或完全没有 INI 对应。

proc 是一个时间点的运行快照。配置字段通常不变，`started`、帧率、占用量和计数器会随着录像、RTSP和拍照状态变化。

## 2. 本次真实业务快照

目前已经确认三个真实状态。

| 快照 | 实际业务 | VENC0 | VENC1 | VENC2/3 |
|---|---|---|---|---|
| S1 | 停止录像，仅副RTSP连接 | H.265已创建、未启动 | H.264 25 fps，约2005 kbps | 未活动 |
| S2 | 默认4K25普通录像，RTSP断开 | H.265 25 fps，约23902 kbps | 已创建、未启动 | VENC3按需产生缩略图 |
| S3 | 普通录像，主/副RTSP连接，在APP中拍照 | H.265活动 | H.264活动 | VENC2序号增加，VENC3产生缩略图 |

HC112的录像模式内拍照入口位于APP中，因此实际可达的抓拍并发是：

```text
普通录像 + 主RTSP + 副RTSP + 4K JPEG抓拍 + JPEG缩略图 + AAC
```

不存在用户可以独立操作的“无RTSP录像模式抓拍”测试状态。

## 3. INI 文件简称

下文使用以下简称。

| 简称 | 文件 |
|---|---|
| M | `config_product_mediamode_cam0_record_2160p30.ini` |
| C | `config_product_mediamode_cam0_comm_record.ini` |
| G | `config_product_mediamode_common.ini` |
| W | `config_product_workmode_record.ini` |
| S | `sceneauto\param\hi3516cv610\sensor_gc8613\config_product_scene_4m25_linear.ini` |

这些媒体 INI 位于：

```text
source\camera\demo\dronecam\modules\param\inicfg\
hi3516cv610\nonescreen\gc8613_128M
```

注意：

- 文件名虽然是 `2160p30`，但 M:3 明确是 `OT_PARAM_MEDIAMODE_2160P_25`；
- 板端运行时读取 `/app/param/param.bin`，不是直接读取散装 INI；
- 真正链路是 `INI → ini2bin → param.bin → PARAM → MEDIA/MAPI/MPI → proc`；
- proc 数值可能经过枚举转换、对齐、单位转换或代码二次覆盖。

## 4. 只读采集命令

### 4.1 系统与绑定

```sh
uname -a
cat /proc/cmdline
ls -l /proc/umap
cat /proc/umap/sys
```

### 4.2 Sensor、ISP、VI、VPSS

```sh
cat /proc/umap/mipi_rx
cat /proc/umap/isp
cat /proc/umap/vi
cat /proc/umap/vpss
```

### 4.3 编码

```sh
cat /proc/umap/venc
cat /proc/umap/h265e
cat /proc/umap/h264e
cat /proc/umap/rc
cat /proc/umap/jpege
cat /proc/umap/chnl
```

### 4.4 内存和图形

```sh
cat /proc/umap/vb
cat /proc/umap/media-mem
cat /proc/umap/rgn
cat /proc/umap/vgs
```

### 4.5 音频

```sh
cat /proc/umap/ai
cat /proc/umap/ab
cat /proc/umap/aenc
cat /proc/umap/adec
cat /proc/umap/ao
cat /proc/umap/acodec
cat /proc/umap/aio
```

### 4.6 辅助节点

```sh
cat /proc/umap/logmpp
cat /proc/umap/ive
cat /proc/umap/md
cat /proc/umap/svp_npu
cat /proc/umap/pm
```

每条命令必须等待重新出现 `~ #` 后再执行下一条，避免串口文本插入上一张表。

## 5. 错误快速索引

遇到问题时先按本表定位，不必从头读全部 proc。

| 故障现象 | 首查节点 | 重点字段 |
|---|---|---|
| Sensor无图、花屏、闪屏 | `mipi_rx` | CRC、ECC、frame mismatch、FIFO overflow、lane状态 |
| ISP帧率异常或统计丢失 | `isp` | `int_rat`、`be_stat_lost`、`ldci_comp_err_cnt`、`sync_id_err_cnt`、`reset_cnt` |
| VI丢帧或拿不到VB | `vi` | `lost_cnt`、`vb_fail_cnt`、`task_fail_cnt`、`vb_reused` |
| VPSS无输出或处理失败 | `vpss` | `preview_lost`、`start_fail`、`malloc_err`、`frame_err`、`dcmp_err` |
| VENC不出流 | `venc` | `started`、`start`、`query_lost`、`full`、`vb_fail`、`query_fail` |
| 编码器丢帧/重编码 | `h265e`/`h264e` | `lost`、`discard`、`p_skip`、`recode`、`unread_stream` |
| 码率或帧率不对 | `rc` | `inst_br`、`inst_fr`、`gop`、QP范围、`lost` |
| JPEG抓拍失败 | `jpege`、`venc` | `pic_droped`、`pic_discard`、`no_stm_cnt`、`rc_fail`、VENC2 sequence/PTS |
| VB不足 | `vb` | `free`、`min_free`、owner、持有模块 |
| MMZ不足 | `media-mem` | `used`、`remain`、各MMB length |
| OSD失败 | `rgn`、`vgs` | `job_fail`、`task_fail`、`end_fail`、`submit_fail`、`int_fail` |
| 音频采集丢失 | `ai`、`ab` | `buf_full_cnt`、`raw_lost`、`user_get/release`、AB `free/min_free` |
| AAC编码异常 | `aenc` | `ai_queue_lost`、`enc_zero`、`frame_err`、`buf_full` |
| 提示音不响 | `adec`、`ao`、`acodec` | send/get/put、AO read/write、mute、DAC power |
| 编码硬件调度错误 | `chnl` | `err_cnt`、`reset`、`start_ok`、通道state |
| NPU/IVE功能未工作 | `svp_npu`、`ive` | task/IRQ计数、错误计数、资源是否全部空闲 |
| 温度异常 | `pm` | `cur_temp`、当前电压及补偿值 |

错误计数应采用“两次采样做差”的方法。历史值非零但不再增长，和持续增长代表的严重程度不同。

## 6. `/proc/umap/sys`

命令：

```sh
cat /proc/umap/sys
```

### 6.1 版本和模块状态

| 字段 | 用途 | HC112实测 | 错误判断 | INI对应 |
|---|---|---|---|---|
| Version/Build Time | 确认MPP组件版本 | V1.0.2.0 B051 | 版本混用需结合加载日志，不单凭日期判错 | 无 |
| SoC标识 | 确认芯片系列 | `0X3516C613` | 与目标板不符才异常 | 无 |
| profile | SYS内核模块运行档位 | 1 | 属于启动参数 | `/proc/cmdline profile=1`，不是媒体INI |
| sys_status | SYS是否运行 | run | 非run时后续媒体模块不能正常工作 | 间接，由SYS初始化决定 |
| audio_status | 音频SYS是否运行 | run | 非run时AI/AO/AENC链路应继续排查 | 间接，由音频编译和初始化决定 |
| 3dnr_pos | 3DNR位置 | n/a | 本版本不展示不等于未开3DNR | 代码/驱动 |

### 6.2 sync frame rate ctrl

| 字段 | 用途 | 错误判断 | INI对应 |
|---|---|---|---|
| src_mod/dev/chn | 帧率同步源 | 表为空表示未建立额外同步控制 | 无直接对应 |
| dst_mod/dev/chn | 帧率同步目标 | 错误目标会造成异常丢帧 | 无直接对应 |
| is_start | 同步控制是否启动 | 仅在配置同步关系时有意义 | 运行状态 |

### 6.3 SYS 工作模式和缩放系数

| 字段组 | 用途 | 错误判断 | INI对应 |
|---|---|---|---|
| capture_mode | SYS采集工作模式 | 当前NORMAL | 代码/驱动 |
| sleep_mode | SYS睡眠模式 | 当前NONE | 电源管理，不对应媒体INI |
| cken_mask | 时钟门控掩码 | 当前0 | 驱动参数 |
| range_level/range_value | 不同缩放比例区间 | 用于选择滤波系数 | 驱动默认 |
| hor_luma/hor_chroma | 水平亮度/色度系数级别 | 画质问题时供底层定位 | 驱动默认 |
| ver_luma/ver_chroma | 垂直亮度/色度系数级别 | 同上 | 驱动默认 |

### 6.4 Bind关系

| 实测Bind | 用途 | INI对应 |
|---|---|---|
| VI0/0 → VPSS0/0 | 图像进入处理组 | C:`vpss.0`的`vcappipehdl/pipechnhdl` |
| VPSS0/0 → VENC0 | 4K H.265主流 | C:`venc.0 modhdl_0=0 chnhdl_0=0` |
| VPSS0/1 → VENC1 | 1024×576 H.264副流 | C:`venc.1 ... chnhdl_0=1` |
| VPSS0/0 → VENC2 | 4K JPEG抓拍 | C:`venc.2 ... chnhdl_0=0` |
| VPSS0/1 → VENC3 | JPEG缩略图 | C:`venc.3 ... chnhdl_0=1` |
| AI0/0 → AENC0 | PCM送AAC编码 | G:`aenc.0 acaphdl=0 acapchdl=0` |
| ADEC0 → AO0/0 | AAC提示音播放 | 运行时播放逻辑 |

`send_cnt`和`rst_cnt`是运行计数，不是INI。某些视频Bind的`send_cnt=0`也可能正常，视频是否送帧应结合VI、VPSS、VENC自己的计数。

## 7. `/proc/umap/mipi_rx`

命令：

```sh
cat /proc/umap/mipi_rx
```

### 7.1 配置与状态字段

| 区域/字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| lane_mode | PHY通道分组方式 | 2+2 | Sensor驱动/板级配置，无媒体INI直接项 |
| port_id | MIPI接收端口 | 0 | Sensor驱动 |
| work_mode | 接口类型 | mipi | C:`vcap.dev input_mode/interface_mode` |
| data_rate | 数据速率模式 | x1 | Sensor驱动 |
| data_type | RAW位宽 | raw_10 | M:`vcap.dev data_type=1` |
| img_rect_x/y | Sensor有效图像起点 | 0/0 | Sensor驱动 |
| img_width/height | 输入尺寸 | 3840×2160 | M:`sensor_width/height` |
| lane_id | 物理lane映射 | 0、2启用 | Sensor驱动/板级配置 |
| wdr_mode | MIPI WDR方式 | none | M:`wdr_mode=0` |
| ext_dt/ext_dt_width | 扩展数据类型及位宽 | 当前未作为主图像使用 | Sensor驱动 |
| sensor_clk/mipi_clk | Sensor和MIPI时钟 | Y/Y | 驱动状态 |
| phy_en/laneN_en | PHY和各lane是否使能 | PHY0、lane0/2使能 | 驱动状态 |
| term_en/lane_map | 端接与内部映射 | 按板级配置 | 驱动 |
| cil_*_cur/nxt_stat | D-PHY当前/下一状态 | 活动lane为HS状态 | 运行状态 |
| freq_measure | 实测PHY频率 | 约1448 MHz | Sensor时序，无媒体INI直接项 |
| mipi_vcN_w/h | 各虚拟通道检测尺寸 | VC0=3840×2160 | 间接对应Sensor规格 |
| laneN_data/mipi_ph/mipi_data | 当前采样数据 | 动态变化 | 无 |

### 7.2 错误字段

| 字段 | 表示什么 | 正常判断 |
|---|---|---|
| clk_fsm_tmout | 时钟lane状态机超时 | 应为0 |
| dN_fsm_tmout | 数据lane状态机超时 | 应为0 |
| clk/dN_fsm_escape | 非预期Escape状态 | 应为0 |
| dN_err_escape | 数据lane Escape错误 | 应为0 |
| vcN_crc_err | 包CRC错误 | 应为0且不增长 |
| vcN_ecc_err | 包头ECC错误 | 应为0且不增长 |
| vcN_frm_num_err | 帧序号错误 | 应为0 |
| vcN_frm_mismatch | 帧结构/尺寸不匹配 | 应为0 |
| rd/wr_data_fifo_err | 数据FIFO读写错误 | 应为0 |
| rd/wr_cmd_fifo_err | 命令FIFO错误 | 应为0 |
| fifo_ovfl/laneN_fifo_ovfl | 总FIFO或lane FIFO溢出 | 应为0 |

出现MIPI错误时，先查供电、MCLK、lane映射和Sensor时序，再查VI；不要先修改VENC。

## 8. `/proc/umap/isp`

命令：

```sh
cat /proc/umap/isp
```

ISP内容很多，可分为“驱动运行状态”“公共图像属性”“3A和图像算法”三类。

### 8.1 模块和运行模式

| 字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| proc_param | proc统计刷新参数 | 30 | 驱动/调试参数 |
| stat_intvl | 统计间隔 | 1 | Scene/ISP内部 |
| update_pos | ISP寄存器更新位置 | 0 | 驱动/ISP |
| int_bothalf | 中断半帧设置 | 0 | 驱动 |
| int_timeout | 中断超时参数 | 30 | 驱动 |
| pwm_number | PWM资源编号 | 7 | 驱动 |
| run_wakeup | 运行唤醒模式 | 0 | 驱动 |
| port_int_delay | 端口中断延迟 | 0 | 驱动 |
| quick_start | 快速启动 | 0 | 驱动/代码 |
| ldci_tprflten | LDCI时域滤波 | 0 | Scene参数 |
| long_frm_int_en | 长帧中断 | 0 | WDR/ISP |
| be_buf_num | ISP BE配置缓冲数 | 8 | 驱动 |
| ob_update_pos | OB更新位置 | frame end | 驱动 |
| alg_run_sel | 算法运行选择 | normal | ISP |
| stitch_mode | 拼接模式 | normal | 当前单Sensor，无媒体INI直接项 |
| running_mode | ISP运行方式 | striping | 驱动根据分辨率/资源选择 |
| block_num | ISP分块数 | 2 | 驱动选择 |
| data_mode | ISP输入数据 | raw | M:`data_type`间接对应 |
| run_once | 单次运行模式 | 0 | 运行状态 |
| sensor_type/dev | Sensor控制总线及设备号 | i2c/0 | Sensor驱动 |

### 8.2 驱动计数和错误

| 字段 | 用途 | 错误判断 |
|---|---|---|
| int_cnt | ISP中断累计数 | 应持续增长 |
| int_t/max/avg | 单次中断处理耗时 | 最大值持续异常升高需关注 |
| int_gap_t/max_gap_t | 帧间隔及最大间隔 | 25 fps附近约40 ms |
| int_rat | 实测帧率 | 当前25 |
| reset_cnt | ISP复位累计数 | 实测历史值2；必须观察是否继续增长 |
| fe_stat_t/cp_stat_t/be_stat_t | FE、统计复制、BE统计耗时 | 性能诊断 |
| be_stat_lost | BE统计丢失 | 应为0 |
| ldci_comp_err_cnt | LDCI计算错误 | 应为0 |
| stitch_pts_cnt | 拼接PTS计数 | 单Sensor通常为0 |
| sync_id_err_cnt | ISP同步ID错误 | 应为0 |
| sensor_cfg_t/max/avg | Sensor寄存器配置耗时 | I²C性能诊断 |
| usr_t/cros_* | 用户算法和跨帧运行耗时 | 性能诊断 |

### 8.3 BE配置和公共属性

| 字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| be_cfg地址 | 各BE配置缓冲物理地址 | 8个缓冲 | 无 |
| free/busy/use/hold_max | BE配置队列占用 | 7/1/1/2 | 运行状态 |
| wnd_x/y/w/h | ISP有效窗口 | 0,0,3840,2160 | M:`isp_width/height` |
| sns_w/h | Sensor尺寸 | 3840×2160 | M:`sensor_width/height` |
| sns_mode | Sensor模式编号 | 0 | M:`sensor_mode=0` |
| flip/mirror | ISP镜像翻转 | 0/0 | M:`isp_mirrorflip`及C:`mirror/flip` |
| bayer | Bayer排列 | rggb | Sensor驱动 |
| crop_en/x/y/w/h | ISP裁剪 | 关闭 | 当前INI未启用 |
| wdr_mode | ISP WDR模式 | linear | M:`wdr_mode=0` |

### 8.4 AE曝光

| 字段组 | 用途 | 错误判断 | 来源 |
|---|---|---|---|
| sys_gain、line、exp | 系统增益、曝光行和曝光量 | 随光照变化，不能和固定INI机械比较 | S场景参数+AE算法 |
| comp、ev_bias、speed、tole、error | AE补偿、速度、容差和当前误差 | error长期很大说明曝光未收敛 | S |
| fps/real_fps | AE配置帧率和实际帧率 | 当前25.00/2500代表25 fps | M+ISP |
| max_line/max_linet | 最大曝光行/时间 | 由Sensor时序决定 | Sensor/S |
| max_agt/max_dgt/max_idgt/max_sgt | 各级最大增益 | Scene/Sensor限制 | S |
| manu_en及ma_* | 手动曝光开关和值 | 当前自动 | S/运行设置 |
| anflick | 防频闪 | 当前开启 | S |
| slow_mod | 慢快门模式 | 当前开启能力 | S |
| gain_th、IR字段 | 增益阈值和红外控制 | 夜间/IR业务诊断 | S/产品代码 |
| again/dgain/isp_dg/iso | 当前模拟、数字、ISP增益和ISO | 动态值 | 运行状态 |
| int_time[] | 各曝光帧积分时间 | Linear主要看第0项 | 运行状态 |
| hmax_times/vmax | Sensor行/帧时序 | 诊断帧率 | Sensor驱动 |

### 8.5 AWB和图像算法

| proc区域 | 字段用途 | 错误/异常怎么看 | INI对应 |
|---|---|---|---|
| AWB | `manuen/sat/zones/speed`为白平衡模式、饱和度、统计分区和收敛速度 | 色偏时看gain、色温是否异常固定 | S |
| ISP AWB | `gain0..3`、`cotemp`、3×3 color matrix | 增益极端或长期不变需查AWB/Sensor | S运行结果 |
| DPC | 坏点校正enable/strength/blend | 画面坏点 | S |
| crosstalk | 串扰校正斜率、阈值、强度 | 彩色串扰 | S |
| FSWDR | WDR运动检测阈值 | 当前Linear下仅作算法状态 | S |
| FPN | 固定噪声校正 | 当前关闭 | S |
| black level | Bayer各通道黑电平 | 黑位偏色/漂移 | S/Sensor |
| BayerNR | 空域/时域降噪强度和运动参数 | 拖影、噪点时看NR档位和ISO | S |
| ACS | 自动色彩阴影校正 | 当前关闭 | S |
| DRC | 动态范围压缩及strength | 暗部、亮部层次 | S |
| dehaze | 去雾及手动强度 | 当前开启、手动强度80 | S |
| CAC | 色差校正阈值和强度 | 紫边、彩边 | S |
| demosaic | 去马赛克强度 | 锯齿、伪色 | S |
| anti false color | 假彩抑制阈值和强度 | 彩色摩尔纹 | S |
| sharpen | 使能、luma/texture/edge数组、频率、overshoot等 | 过锐、白边、噪声放大 | S |
| LDCI | 局部对比度、正负权重等 | 局部亮暗异常 | S |
| CA | 色彩调整使能和ISO比例 | 饱和度/色彩 | S |
| alg run time | 各算法耗时和总耗时 | 总耗时接近帧周期会有性能风险 | 运行统计 |

Sharpen、NR等数组每个下标通常对应亮度、ISO或运动等级。它们来自Scene参数，不对应M/C/G/W四份媒体INI。

## 9. `/proc/umap/vi`

命令：

```sh
cat /proc/umap/vi
```

### 9.1 模块、Dev、Pipe配置

| proc区域/字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| module max_out_width/height | VI最大输出能力 | 4096×4096 | 驱动能力 |
| detect_err_frame/drop_err_frame | 错帧检测和丢弃开关 | 0/0 | 驱动参数 |
| vi_vpss_mode | VI与VPSS在线/离线关系 | pipe0为offline→online | M:`vivpssmode=1` |
| vi_aiisp_mode | AIISP模式 | default | 当前`aibnr_support=0` |
| dev_status | VI设备是否使能 | dev0 enable | C:`vcap.dev enable=1` |
| intf_mode | 输入接口 | mipi | C:`interface_mode=5` |
| work_mode | 多路复用方式 | 1mux | 单Sensor配置 |
| comp_mask0/1 | 分量掩码 | `ffc00000/0` | M:`componentmask0/1` |
| scan_mode | 扫描方式 | progressive | Sensor驱动 |
| data_seq/data_type | 数据顺序和RAW/YUV类型 | yvyu/raw | C:`datasequce/inputdatatype` |
| width/height | VI设备输入尺寸 | 3840×2160 | M:`sensor_width/height` |
| data_rate | 数据速率 | x1 | Sensor驱动 |
| valid/total width等 | 实际时序检测 | 诊断Sensor行场时序 | Sensor驱动 |
| bind attr | dev绑定到哪些pipe | dev0→pipe0 | M/C pipe0配置 |
| pipe attr1 | bypass、ISP bypass、尺寸、RAW位宽、压缩 | 3840×2160 RAW10 none | M:`vcap.pipe.0` |
| pipe attr2 | 对齐、src/dst fps、帧源、VC、VB来源 | 25→25、VC0、common | M:`src/dst_framerate` |

### 9.2 Pipe处理字段

| 字段组 | 用途 | 错误判断 | INI对应 |
|---|---|---|---|
| discard_pic_en | 是否主动丢图 | 当前N | 代码/驱动 |
| out_mode/data_rate | 输出模式与数据率 | norm/x1 | 驱动 |
| yuv_skip_en | YUV跳过模式 | 当前Y | 驱动实现 |
| bnr_info_en | 是否输出BNR信息 | 当前N | ISP/VI |
| nr_effect_mode | 降噪效果模式 | advance | Scene/驱动 |
| bnr_buf_num | BNR缓冲数 | 2 | 驱动资源 |
| post crop | Pipe后裁剪 | 关闭 | 当前INI无裁剪 |
| pipe 3dnr attr | 3DNR使能、类型、压缩、运动模式 | 开、NORM | C:`vpss/NR`及驱动 |
| pipe 3dnr param | 各级时空降噪参数 | 画面噪声/拖影诊断 | S |
| dump attr | Pipe dump开关和depth | 关闭 | 调试运行设置 |
| low delay | 低延迟、line、one_buf | 开、1000行 | C:`lowdelayenable/line` |
| frame interrupt | 中断类型和early_line | start、2060 | M:`frameinterrupt_type/earlyline` |
| user pic | 用户替代图像 | 关闭 | 运行设置 |
| wrap status | 环形缓冲配置和错误 | 当前关闭 | 代码/运行模式 |

### 9.3 VI错误和性能字段

| 区域/字段 | 表示什么 | 正常判断 |
|---|---|---|
| pipe status `int_cnt/send_cnt` | 中断和送出帧数 | 持续增长，通常相差一帧在途 |
| `lost_cnt` | Pipe丢帧 | 应为0 |
| `vb_fail_cnt` | 申请VB失败 | 应为0 |
| `vb_reused` | VB被复用次数 | 当前应为0 |
| frame_rate | 实际帧率 | 25 |
| offline task `receive_pic_cnt` | 离线任务收图数 | 持续增长 |
| `busy_num` | 当前忙任务数 | 瞬时值 |
| `task_submit_cnt` | 提交任务数 | 持续增长 |
| `task_fail_cnt` | 任务提交失败 | 应为0 |
| `task_cost/max_cost` | VI离线任务耗时 | 性能诊断 |
| chn status `send_cnt/lost_frame_cnt/vb_fail_cnt` | 物理通道输出统计 | 该模式可能显示chn disabled，需结合Pipe/VPSS |
| interrupt cost/load_ratio | VI中断耗时和负载 | 持续过高需要关注 |

本机是VI offline→VPSS online模式，`vi phys chn status`可能显示`enable=N`，但Pipe和VPSS计数正常增长。这不是VI失败。

## 10. `/proc/umap/vpss`

命令：

```sh
cat /proc/umap/vpss
```

### 10.1 配置字段

| 区域/字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| module schedule_mode | VPSS调度方式 | NORMAL | 驱动 |
| max_out_width/height | 最大处理尺寸 | 4096×4096 | 驱动能力 |
| high_profile | 高规格模式 | N | 驱动 |
| grp cfg | rotation/DIS/运动降噪能力 | 当前均N | 驱动能力 |
| max_split_num/max_out_rgn_num | 最大分块和区域数 | 2/1 | 驱动能力 |
| grp max_w/max_h | 组最大输入 | 3840×2160 | M:`vpss.0 max_width/height` |
| grp pixel_fmt | 输入像素格式 | YVU-SP420 | C:`vpss.0 pixelformat=0` |
| src/dst rate | 组帧率 | 25→25 | M:`vpss.0 src/dst_framerate` |
| user_ctrl/backup | 用户控制和备份帧 | Y/N | MAPI/驱动 |
| buf_share_en | 组缓冲共享 | N | 通道配置间接影响 |
| DCI/IE/DEI | 图像增强和去隔行 | 关闭 | 当前INI无对应启用 |
| grp crop | 组裁剪 | 关闭，trim=3840×2160 | C:`cropenable=0`、M裁剪值 |
| svc param | SVC输入设置 | 关闭 | 当前编码SVC关闭 |
| chn0 | 3840×2160、25 fps | 主流/大图来源 | M:`vport.0`、C:`vport.0 enable=1` |
| chn1 | 1024×576、25 fps | 副流/缩略图来源 | M:`vport.1`、C:`vport.1 enable=1` |
| chn2 | 未创建活动输出 | C:`vport.2 enable=0` |
| mode | 通道尺寸由用户指定 | USER | MAPI转换 |
| align | 输出对齐 | 8 | 驱动/MAPI |
| depth | 用户取帧队列深度 | 0 | MAPI |
| aspect/video rect/border | 宽高比和边框 | 当前NONE/关闭 | 当前INI未设置 |
| sharpen/quick_send/scale_type | VPSS锐化、快送、缩放算法 | 关闭/NORMAL | 驱动/代码 |
| wrap/low delay/LDC | 环形缓冲、低延迟、畸变校正 | 当前关闭 | C中对应enable=0 |

### 10.2 错误和动态字段

| 字段 | 表示什么 | 正常判断 |
|---|---|---|
| node free/busy/delay | VPSS节点队列状态 | 不应长期无free或大量delay |
| recv_pic/new_do/old_do | 收图和任务处理计数 | 活动时增长 |
| preview_lost | 预览丢帧 | 应为0 |
| new_undo/old_undo | 未完成任务 | 不应持续堆积 |
| start_fail | 启动任务失败 | 应为0 |
| chn send_ok | 各端口成功送帧数 | ch0/ch1同步增长 |
| chn frame_rate | 实测输出帧率 | 统计窗口可能显示25或26 |
| link_int | VPSS硬件中断数 | 活动时增长 |
| bus_err/dcmp_err/frame_err | 总线、解压、帧错误 | 应为0 |
| malloc_err/free_err | 内存申请/释放错误 | 应为0 |
| start_err/node_err | 硬件启动/节点错误 | 应为0 |
| load_ratio | VPSS硬件负载 | 性能参考 |

## 11. `/proc/umap/venc`

命令：

```sh
cat /proc/umap/venc
```

### 11.1 通道静态属性

| 字段 | 用途 | 当前四通道 | INI对应 |
|---|---|---|---|
| id | VENC通道号 | 0/1/2/3 | C:`venchdl` |
| width/height | 编码分辨率 | 4K、1024×576、4K、320×180 | M:`venc.N res_width/height` |
| type | 编码类型 | H265/H264/JPEG/JPEG | C:`payload` |
| by_frame | 按帧输出 | 全部Y | C:`isByFrame=1` |
| sequence | 通道累计序号 | 活动时递增 | 运行状态 |
| gop_mode | GOP结构 | H26x为normal_p | 代码固定NORMALP |
| priority | 编码优先级 | 0 | MAPI/驱动 |
| fast_enc | 快速编码 | 仅VENC0为Y | `media_venc.c`代码覆盖 |
| quality_level | 质量级别 | 1 | 驱动/代码 |
| dup_frame_strategy | 重复帧策略 | RECODE | 驱动 |
| one_pack | 单包输出策略 | N | 驱动模块参数 |

### 11.2 通道运行字段

| 字段 | 用途 | 错误判断 |
|---|---|---|
| started | 是否正在接收输入帧 | 必须结合业务状态判断 |
| src/dst_frame_rate | VENC接收控制值 | 本版本显示-1时看RC实际fps |
| time_ref | 编码时间参考 | 活动时增长 |
| pixel_format | 输入像素格式 | H26x和实际JPEG均为YVU420 |
| pic_addr | 当前输入帧地址 | 0可能表示当前无在途帧 |
| in_depth | 输入队列深度 | 当前3 |
| start/start_ex | 接收启动状态 | 连续编码活动时start=1 |
| recv_left/enc_left | 待接收/待编码数量 | 不应持续堆积 |
| left_bytes/left_frm/cur_packs | 未取走码流 | 持续非零增长表示消费者慢 |
| buf_full_cnt | 通道buffer满次数 | 应为0 |

### 11.3 VENC错误表

| 表/字段 | 表示什么 | 正常判断 |
|---|---|---|
| vpss query `query_lost` | 查询输入帧丢失 | 0 |
| `invalid/full/vb_fail` | 无效、队列满、VB失败 | 0 |
| `query_fail/info_err` | 查询失败或帧信息错误 | 0 |
| send1 `vpss_err/other_err` | VPSS或其他来源送帧失败 | 0 |
| `full/crop_err/size_err` | 通道满、裁剪错误、尺寸错误 | 0 |
| send2 `start_fail/interrupt_fail` | VGS辅助任务启动/中断失败 | 0 |
| channel `ch_reso_lost` | 分辨率不匹配丢帧 | 0 |
| `over_load` | 编码硬件过载 | 0 |
| `ring_skip/rc_skip/zme_skip` | 环形缓冲、码控、缩放跳帧 | 0 |
| stream `user_get/user_release` | 用户取流/释放 | 应相等或仅差当前在途帧 |
| busy/user_cnt | 码流队列占用 | 不应持续堆积 |

### 11.4 三个业务状态怎样解释

| 业务状态 | VENC0 | VENC1 | VENC2 | VENC3 |
|---|---|---|---|---|
| S1仅副RTSP | N | Y，25 fps | N | N |
| S2普通录像无RTSP | Y，25 fps | N | N | 单帧短时使用 |
| S3录像+双RTSP+APP拍照 | Y | Y | 抓拍后回N、sequence增加 | 缩略图sequence增加 |

`started=N`不等于创建失败。HC112将“创建通道”和“开始接收”分开，并按消费者引用计数启停。

## 12. `/proc/umap/h265e`

命令：

```sh
cat /proc/umap/h265e
```

### 12.1 属性和高级参数

| 区域/字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| one_pack | 编码输出单包模式 | 1 | 驱动模块参数 |
| h265_vb_src | H.265 VB来源 | private | 驱动 |
| power_save_en | 编码器省电 | 1 | 驱动 |
| mini_buf_mode | 小码流buffer模式 | 1 | 驱动 |
| qp_hist_en | QP直方图 | 0 | 驱动 |
| max_width/height | 通道最大尺寸 | 3840×2160 | M:`venc.0` |
| width/height | 当前编码尺寸 | 3840×2160 | M |
| profile | H.265 Profile | mp/Main | G:`venc.video.main.h265 profile=0` |
| color_to_grey | 灰度编码 | N | 当前INI未启用 |
| buf_size | 码流buffer | 3110400 | M:`venc.0 bufsize` |
| by_frame | 按帧 | Y | C:`isByFrame=1` |
| gop_mode | GOP模式 | normal_p | 代码固定 |
| max_stream_cnt | 最大缓存流数 | 800 | 驱动 |
| pred_en/base/enhance | 参考帧预测和基础/增强层 | Y/1/0 | G:`ref_enable_pred/ref_base/ref_enhance` |
| used/max_used_frame | 当前/最大参考帧使用量 | 动态 | 驱动运行状态 |
| rcn_ref_share_buf_en | 重构参考帧共享 | Y | MAPI/驱动 |
| frame_buf_ratio | 帧buffer比例 | 80 | 驱动 |
| slice_split | Slice切分 | 关闭 | 当前代码/默认 |
| intra_refresh | 帧内刷新 | 关闭 | C:`venc.0.intraRefresh refreshEnable=0` |
| dblk/tc/beta | 去块滤波及偏移 | 开、0、0 | 代码/驱动 |
| across_slc/tile | 跨slice/tile滤波 | 开 | 代码/驱动 |
| sao_luma/chroma | SAO | 0/0 | `media_venc.c`代码覆盖 |
| constrained_intra | 受限帧内预测 | 0 | 驱动 |
| intra_smoothing | 帧内平滑 | 1 | 驱动 |
| cb/cr_qp_offset | 色度QP偏移 | -3/-3 | 驱动/代码 |
| scene_mode | 场景模式 | scene_2 | G:`scene_mode=2` |
| bitrate_strategy | 码率策略 | auto | 驱动 |
| skip/md/deblur | 跳过、运动检测、去模糊高级项 | 当前关闭 | 代码/驱动，无直接媒体INI |

### 12.2 错误字段

| 字段 | 表示什么 | 正常判断 |
|---|---|---|
| enc_start/enc_succeed | 开始和成功编码帧数 | 通常仅差一帧在途 |
| copy | 复制编码次数 | 业务相关 |
| lost | 编码丢帧 | 0 |
| discard | 主动丢弃 | 0 |
| p_skip | P帧跳过 | 当前0 |
| recode | 重编码次数 | 当前0 |
| release_stream | 已释放码流 | 应接近成功帧数 |
| unread_stream | 未读码流 | 不应持续增加 |
| stream data_len/buf_free | buffer占用和剩余 | data_len不应持续增长 |

S2实测H.265 `enc_start=273`、`enc_succeed=272`，仅一帧在途，错误项均为0。

## 13. `/proc/umap/h264e`

命令：

```sh
cat /proc/umap/h264e
```

H.264字段与H.265大部分含义相同，差异如下。

| 字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| id | H.264通道 | 1 | C:`venc.1` |
| width/height | 副码流尺寸 | 1024×576 | M:`venc.1` |
| profile | H.264 Profile | hp/High | G:`venc.video.sub.h264 profile=2` |
| buf_size | 码流buffer | 294912 | M:`venc.1 bufsize` |
| ref参数 | 参考帧设置 | pred=Y、base=1 | 驱动/G公共参数 |
| entropy_i/p | I/P熵编码 | CABAC | High Profile正常 |
| entropy_b | B帧熵编码 | CAVLC | 当前normal_p无B帧 |
| trans_i/p | 变换模式 | all | 驱动 |
| scaling_list_valid | Scaling List | N | 驱动默认 |
| dblk_idc/alpha/beta | 去块滤波 | 0/0/0 | 驱动 |
| scene_mode | 场景模式 | scene_2 | G:`venc.video.sub scene_mode=2` |
| intra_refresh | 帧内刷新 | 关闭 | C:`venc.1.intraRefresh` |
| fast_enc | 快速编码 | VENC总节点显示N | 代码仅对handle0开启 |

S1仅副RTSP时：

- H.264 `enc_start=3756`、`enc_succeed=3756`；
- lost、discard、p_skip、recode、unread均为0；
- stream `data_len=0`，说明APP正常取流。

## 14. `/proc/umap/rc`

命令：

```sh
cat /proc/umap/rc
```

### 14.1 基础码控参数

| 字段 | VENC0 | VENC1 | INI对应 |
|---|---:|---:|---|
| type | H.265 | H.264 | C:`payload` |
| mode | QVBR | CBR | C:`rcmode=2/0` |
| gop | 25 | 25 | M:`gop` |
| stats_time | 2 s | 2 s | M:`stat_time` |
| src/dst fps | 25/25 | 25/25 | M:`src/dst_framerate` |
| bitrate | 22528 kbps | 2048 kbps | M:`h265bitrate/h264bitrate` |
| min/max QP | 25/51 | 10/51 | G对应codec+RC节点 |
| min/max I QP | 25/51 | 10/45 | G对应codec+RC节点 |
| idr_en | Y | Y | MAPI/驱动 |
| qpmap_en | N | N | 当前未启用 |

### 14.2 运行公共参数

| 字段组 | 用途 | INI对应 |
|---|---|---|
| row_qp_delta | 行级QP变化 | MAPI/驱动 |
| threshold_i/p/b[16] | 不同复杂度的QP阈值表 | 驱动默认 |
| first_frame_start_qp | 首帧起始QP，-1为自动 | 驱动 |
| direction | 阈值方向 | 驱动 |
| lost/threshold/lost_mode | 丢帧控制 | 驱动 |
| frame_gap | 丢帧间隔 | 驱动 |
| base_qp_delta | 基础QP偏移 | 驱动 |
| super_frame_mod/threshold | 超大帧控制 | 当前none |
| rc_priority | 码控优先目标 | bitrate | 驱动 |
| detect_scene_chg_en | 场景切换检测 | 当前N，代码设置 |
| adapt_insert_idr_frame_en | 自动插IDR | 当前N，代码设置 |
| out_rc_en | 外部码控 | 当前N |
| fg protect | 前景保护阈值和增益 | 当前关闭 | 驱动 |
| gop_mode/ip_qp_delta | GOP模式及IP QP差 | normal_p/1 | 代码固定 |
| max_reencode_times | 最大重编码次数 | 0 | `media_venc.c`覆盖 |

### 14.3 CBR/QVBR专用参数

| 字段 | VENC0 QVBR | VENC1 CBR | INI对应 |
|---|---:|---:|---|
| min/max bit percent | 45/100 | 不适用 | G:`bit_percent_ll/ul` |
| min/max PSNR fluctuate | 23/30 | 不适用 | G:`psnr_fluctuate_ll/ul` |
| min/max I proportion | 1/100 | 1/20 | 驱动/MAPI |
| chg_pos | 100 | 不适用 | 驱动 |

### 14.4 实际码率和错误判断

| 字段 | 用途 | 判断方法 |
|---|---|---|
| inst_br | 瞬时码率kbps | 活动通道应接近策略目标；QVBR允许波动 |
| inst_fr | 实际帧率 | 活动通道应为25 |
| cfg_bit/real_bit | 配置和实时码控内部统计 | 供底层码控诊断 |
| ip_ratio | I/P帧码量比例 | 随场景变化 |
| start_qp | 起始QP | 应处于合理范围 |
| min_qp/max_qp | 运行期QP边界 | 长期顶到max说明码率或场景压力大 |
| lost | 码控丢帧开关/状态 | 当前N |
| debreath_effect | 呼吸效应抑制 | 当前关闭 |
| hierarchical_qp | 分层QP | G:`venc.hierarchical.qp enable=0` |

实测：

- S1副H.264约2005 kbps、25 fps，符合2048 kbps CBR；
- S2主H.265约23902 kbps、25 fps。QVBR瞬时高于22528不能单点判错，应看长期平均、QP和画质。

## 15. `/proc/umap/jpege`

命令：

```sh
cat /proc/umap/jpege
```

| 区域/字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| one_pack | 单包输出 | 1 | 驱动 |
| mini_buf_mode | 小buffer模式 | 1 | 驱动 |
| jpeg_clear_stream_buf | 停止时清流buffer | 1 | 驱动 |
| id | JPEG通道 | 2/3 | C:`venc.2/3` |
| is_mjpeg | 是否MJPEG | N | C:`payload=JPEG` |
| pic_type | 输入格式 | yvu420 | VPSS输出 |
| width/height | 图片尺寸 | 4K、320×180 | M:`venc.2/3` |
| buf_size | JPEG编码buffer | 4147200、43200 | M:`bufsize` |
| by_frm | 按帧 | Y | C:`isByFrame=1` |
| color_to_grey | 灰度 | N | 当前未启用 |
| dcf | DCF信息 | N | G:`enable_dcf=0` |
| qfactor | JPEG质量 | 95 | G:`quality_factor=95` |
| dering | 去振铃 | 开 | 驱动 |
| dblk/batch_crop | 去块/批裁剪 | 关闭 | 驱动/当前配置 |

### JPEG错误字段

| 字段 | 表示什么 | 正常判断 |
|---|---|---|
| pic_recv/pic_coded | 接收/成功编码图片数 | 一次请求后应相等 |
| pic_droped | 图片丢失 | 0 |
| pic_discard | 图片被丢弃 | 0 |
| no_stm_cnt | 无码流buffer | 0 |
| rc_fail | JPEG码控失败 | 0 |
| pic_recode | JPEG重编码 | 当前0 |
| unread_stream | 未读JPEG | 不应积压 |
| data_len/buf_free | 码流buffer占用 | 请求结束后应释放 |

S3中VENC2 `sequence=2`并出现有效PTS，证明4K JPEG已编码。随后JPEGE的`pic_recv/pic_coded`又显示0，是因为`jpeg_clear_stream_buf=1`且单拍通道已经停止/清理，不能据此判断拍照失败。抓拍是否成功要同时看：

1. VENC2 sequence是否增加；
2. VENC2 PTS是否非0；
3. APP是否收到文件/回调；
4. JPEGE错误计数是否非0。

## 16. `/proc/umap/chnl`

命令：

```sh
cat /proc/umap/chnl
```

| 字段 | 用途 | 错误判断 |
|---|---|---|
| scheduler_id/vpu_num | 编码调度器和硬件单元数 | 资源说明 |
| VPU name/state | VEDU或JPGE运行状态 | 有活动H26x时VEDU应run |
| int_cnt/timer_cnt/vpu_cnt | 中断、定时、任务累计数 | 活动时增长 |
| err_cnt | 硬件调度错误 | 应为0 |
| query_cnt/start_ok/config_ok | 查询、启动、配置成功次数 | 失败时结合日志 |
| reset | VPU复位次数 | 应为0或不持续增长 |
| chn state | 每个H265/H264/JPEG任务状态 | 与started/业务一致 |
| task_num | 当前任务数 | 活动通道通常非0 |
| interrupt_num | 通道完成中断 | 活动时增长 |
| current run state | 当前VPU正在处理哪个通道 | 双编码时可轮转 |
| cost/hw_cycle | 调度和硬件耗时 | 性能诊断 |

这些字段没有INI直接对应。通道类型和创建数量间接来自VENC配置。

## 17. `/proc/umap/vb`

命令：

```sh
cat /proc/umap/vb
```

### 17.1 公共池配置

| INI值 | proc实际值 | count | 说明 |
|---:|---:|---:|---|
| 10575360 | 10575360 | 0 | 规格占位，不创建Block |
| 8311768 | 8311808 | 3 | 驱动向上对齐40字节 |
| 884736 | 884736 | 4 | 一致 |
| 86400 | 86528 | 3 | 驱动向上对齐128字节 |

来源为M:`vb.pool.N blk_size/blk_count`。`max_pool_cnt=96`是驱动上限，不等于M中的`max_poolcnt=4`。

### 17.2 字段说明

| 字段 | 用途 | 错误判断 |
|---|---|---|
| pool_id | 驱动实际池号 | 应按size识别，不只看编号 |
| phys_addr/virt_addr | 池物理/虚拟地址 | 调试信息 |
| pool_type | common或private | 区分INI公共池和模块私有池 |
| owner | 池创建者 | common、VI、H265E、H264E等 |
| blk_sz/blk_cnt | Block规格和总数 | 应满足目标帧规格 |
| free | 当前空闲数 | 瞬时值 |
| min_free | 启动以来最低空闲数 | 判断余量的关键 |
| reserve | 保留Block数 | 当前0 |
| state | 池状态 | idle不表示无人引用 |
| vi/venc/h265e等列 | 每块由哪些模块引用 | 查Block生命周期 |
| get | 最近获取者/当前归属提示 | 调试 |
| free_bytes | Block内部剩余 | 对齐/子分配参考 |

### 17.3 当前业务占用

| 状态 | 8311808池 | 884736池 | 86528池 |
|---|---|---|---|
| S1仅副RTSP | free=2，VPSS占1 | free=3 | free=3 |
| S2普通录像 | free=1，VENC0和VPSS各占1 | free=3 | free=3 |
| S3录像+双RTSP+拍照后 | free=1 | free=2，VENC1和VPSS各占1 | free=3 |

重要错误判断：

- `free=0`本身不一定错误，要结合`min_free`、VI/VPSS/VENC的`vb_fail`；
- 某个小池耗尽，其他大池有空闲也未必能替代；
- 不能因为S2还有空闲就减少Block，最坏状态是S3；
- 私有池`free=0`可能表示编码器正常长期持有重构帧，不等于泄漏。

## 18. `/proc/umap/media-mem`

命令：

```sh
cat /proc/umap/media-mem
```

| 字段 | 用途 | INI对应 |
|---|---|---|
| ZONE PHYS范围 | MMZ物理地址区间 | `/proc/cmdline mmz_zones` |
| GFP | MMZ zone编号/属性 | 启动参数 |
| nBYTES | zone总大小 | `/proc/cmdline` |
| MMB phys/kvirt | 每个分配块地址 | 无 |
| flags/kernel_only/share_all | 缓存、内核和共享属性 | 驱动 |
| pid[] | 持有进程 | 运行状态 |
| length | 分配长度 | 间接受VB/VENC配置影响 |
| name | 分配用途 | 驱动/模块命名 |
| total/used/remain | MMZ总量、已用、剩余 | 运行状态 |

常见MMB名称：

| 名称 | 用途 |
|---|---|
| `vb_pool` | 公共VB池 |
| `vi(0)_one_buf_pool` | VI低延迟/单buffer池 |
| `vi(0)_bnr_*`、`3dnr_*` | BNR/3DNR参考和统计 |
| `isp[0].*` | ISP寄存器、统计和BE配置 |
| `h265e0_stm/rcn/info` | H.265码流、重构帧和信息块 |
| `h264e1_stm/rcn/info` | H.264码流、重构帧和信息块 |
| `jpege2/3_stm` | JPEG码流buffer |
| `rgn_*` | OSD bitmap/canvas |
| `ai/aenc/ao` | 音频帧、码流和DMA |
| `Ringbuf` | 录像环形缓冲区 |

本机MMZ约82 MiB。`remain`持续接近0并伴随模块申请失败才是明确内存问题。`media-mem`总使用量不能和公共VB总和画等号。

## 19. `/proc/umap/rgn`

命令：

```sh
cat /proc/umap/rgn
```

### 19.1 Overlay字段

| 字段 | 用途 | INI对应 |
|---|---|---|
| hdl/type | RGN句柄和类型 | W:`osd.0..5` |
| used | 当前画布是否在使用 | 动态状态 |
| pixel_format | bitmap格式 | 实测ARGB1555，OSD实现 |
| width/height | 实际OSD bitmap尺寸 | 由字体、内容、基础分辨率动态计算 |
| bg_color | bitmap背景色 | W:`bg_color`，可能转换 |
| phys/virt | OSD内存地址 | 无 |
| stride | 每行字节跨度 | 由宽度和像素格式对齐 |
| canvas_num/buf0/buf1 | 画布数量和使用状态 | OSD实现 |

### 19.2 绑定和位置

| 字段 | 用途 | INI对应 |
|---|---|---|
| mod/dev/chn | OSD绑定模块、设备、通道 | W:`bind_module/modhdl/chnhdl` |
| is_show | 是否显示 | W:`show` |
| x/y | 实际像素坐标 | W:`start_x/start_y`按base resolution缩放后得到 |
| fg_alpha/bg_alpha | 前景/背景透明度 | W同名字段 |
| layer | OSD层级 | 默认0 |
| is_abs_qp/qp_val/qp_enable | OSD区域QP控制 | 当前关闭 |

实测6个句柄绑定：

- handle0/1/4绑定VENC0和VENC2；
- handle2/3/5绑定VENC1；
- S3主副连接和拍照状态下6个画布均为used。

### 19.3 错误字段

| 字段 | 表示什么 | 正常判断 |
|---|---|---|
| call_cnt | 调用VGS次数 | 活动OSD增长 |
| job_suc/job_fail | VGS job成功/失败 | fail应为0 |
| task_suc/task_fail | VGS task成功/失败 | fail应为0 |
| end_suc/end_fail | job结束成功/失败 | fail应为0 |

## 20. `/proc/umap/vgs`

命令：

```sh
cat /proc/umap/vgs
```

| 区域/字段 | 用途 | 错误判断 |
|---|---|---|
| max_job/task/node_num | VGS资源上限 | 驱动能力 |
| recent job mod_name | 最近调用者，如VPSS/RGN | 判断谁在使用VGS |
| job_hdl/task_num/state | 任务句柄、数量和状态 | 不应长期卡在异常状态 |
| in_size/out_size | 输入输出帧大小 | 判断缩放/搬运 |
| cost_time/hw_time | 软件和硬件耗时 | 性能诊断 |
| crop/cover/mosaic/osd/zme等 | 任务使用的功能 | 运行状态 |
| video/pixel/cmp转换 | 输入输出格式转换 | 与VPSS/RGN任务有关 |
| success/fail/cancel | job和task结果 | fail/cancel应为0 |
| free/busy/procing | 资源队列状态 | 不应长期无free |
| submit_fail/int_fail | 提交和中断失败 | 应为0 |
| err_int/start_err/node_err | 硬件错误 | 应为0 |
| load_ratio | VGS负载 | 性能参考 |

VGS大部分没有直接INI对应，它是VPSS、RGN等模块内部调用的硬件处理单元。

## 21. `/proc/umap/ai`

命令：

```sh
cat /proc/umap/ai
```

### 21.1 配置字段

| 字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| ai_dev | AI设备号 | 0 | G:`acapture.0 handle=0` |
| i2s_type/work_mode | 内置I²S及主从模式 | inner/i2s_mas | G:`work_mode=0` |
| sample_rate | 采样率 | 16 kHz | G:`sample_rate=16000` |
| bit_width | 位宽 | 16 bit | G:`bit_width=1` |
| chn_cnt | 底层设备通道数 | 2 | Codec设备能力 |
| clk_share | 时钟共享 | 1 | 驱动 |
| snd_mode | 单/双声道 | mono | G:`sound_mode=0` |
| point_num | 每帧采样点 | 1024 | G:`ptnum_per_frm=1024` |
| frame_num | 帧队列数量 | 5 | MAPI/驱动 |
| track_mode | 声道映射 | 0 | G:`track_mode=0` |
| mute | 静音 | N | 运行设置 |
| volume/dmic_gain | AI软件音量/数字麦增益 | 0/0 | 不能直接等同`audiogain` |

### 21.2 状态和错误

| 字段 | 表示什么 | 正常判断 |
|---|---|---|
| interrupt_cnt | AI中断累计 | 持续增长 |
| fifo_cnt | FIFO异常/占用计数 | 当前0 |
| buf_full_cnt | AI buffer满 | 0 |
| frame_time/min/max | 音频帧周期 | 1024/16k约64 ms |
| trans_len | DMA传输长度 | 当前4096 |
| isr_time/min/max | 中断处理耗时 | 性能诊断 |
| cb_phys/cb_size/read/write offset | 环形DMA buffer状态 | 调试 |
| chn state | AI通道是否enable | ch0 enable |
| depth/data0/data1 | 通道队列深度和数据状态 | 不应持续堆积 |
| user_get/user_release | 用户取帧/释放 | 应相等 |
| raw_lost | RAW音频帧丢失 | 0 |
| resample_open/in/out rate | 重采样状态 | 当前关闭 |

### 21.3 VQE

| 字段 | 用途 | INI对应 |
|---|---|---|
| vqe_open/type | VQE使能和类型 | G:`enable_vqe=1` |
| rate/point_num | VQE采样率/帧点数 | G音频参数 |
| ANR/AGC/AEC/EQ/HPF/RNR/DRC | 各音频处理算法开关 | VQE配置文件/默认参数 |
| usr_mode | 是否使用用户参数 | 运行设置 |
| hpf_freq | 高通截止频率 | 实测80 Hz |
| AGC target/max_gain等 | 自动增益参数 | VQE参数 |
| RNR阈值/等级 | 混响/噪声抑制 | VQE参数 |
| DRC attack/release/level | 动态范围压缩 | VQE参数 |

## 22. `/proc/umap/ab`

命令：

```sh
cat /proc/umap/ab
```

AB是Audio Block池。

| 字段 | 用途 | HC112实测 | 错误判断 |
|---|---|---|---|
| max_pool_cnt | 最大音频池数 | 4 | 驱动能力 |
| ab_cnt | Audio Block总数 | 24 | MAPI/驱动 |
| blk_sz | 每块大小 | 4096 | 与1024点×设备通道×16bit有关 |
| blk_cnt | Block数量 | 24 | 音频队列资源 |
| free/min_free | 当前/最低空闲 | 19/18 | 长期0表示音频Block不足或未释放 |
| ai/aenc/user | 每块引用者 | 实测主要由AI持有 | 查泄漏/积压 |

AB没有媒体INI中的独立Pool配置，大小由AI属性和驱动计算。

## 23. `/proc/umap/aenc`

命令：

```sh
cat /proc/umap/aenc
```

| 字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| chn_id | AENC通道 | 0 | G:`aenc.0 aenchdl=0` |
| payload_type | 编码格式 | AAC | G:`aenc.0.aac` |
| point_num | 每帧采样点 | 1024 | G:`ptnum_per_frm=1024` |
| buf_size | 码流队列深度/大小参数 | 300 | MAPI/驱动 |
| recv_frame | 收到AI帧数 | 活动时增长 | 运行状态 |
| enc_ok | 成功编码数 | 应等于recv或仅差在途帧 | 运行状态 |
| get/release_stream | 用户取流/释放 | 应相等 | 运行状态 |
| mute | 编码静音 | N | 运行设置 |

错误字段：

- `ai_queue_lost`：AI→AENC队列丢帧；
- `enc_zero`：编码产生空帧；
- `frame_err`：输入帧错误；
- `buf_full`：AENC码流buffer满。

上述字段应为0。AAC-LC、48 kbps、16 kHz、mono、ADTS等更详细属性来自G:207-215，但当前AENC proc没有全部展示。

## 24. `/proc/umap/adec`

命令：

```sh
cat /proc/umap/adec
```

| 字段 | 用途 | 错误判断 | INI对应 |
|---|---|---|---|
| chn_id/payload | 解码通道和格式 | 当前AAC ch0 | 提示音播放代码 |
| buf_size | 解码输入buffer | 50 | MAPI/驱动 |
| mode | stream或pack模式 | 当前stream | 播放代码 |
| orig_send_cnt/send_cnt | 原始送流和实际送流数 | 应相等 |
| get_cnt/put_cnt | 解码帧获取和送出 | 应相等 |

ADEC不属于录像音频输入链。它只服务AAC提示音，W/G没有独立ADEC通道配置。

## 25. `/proc/umap/ao`

命令：

```sh
cat /proc/umap/ao
```

| 字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| ao_dev | AO设备 | 0 | G:`ao.0 handle=0` |
| i2s/work_mode | 内置I²S主模式 | inner/i2s_mas | G:`work_mode=0` |
| sample_rate/bit_width | 播放格式 | 16 kHz/16 bit | G:`sample_rate/bit_width` |
| chn_cnt/snd_mode | 设备通道数和声道模式 | 2/stereo | G:`sound_mode=1` |
| point_num/frame_num | 每帧点数和队列帧数 | 1024/4 | G+驱动 |
| track_mode/mute/volume | 声道映射、静音、软件音量 | 0/N/0 | G:`track_mode/volume`经Codec转换 |
| interrupt_cnt | AO中断数 | 设备运行时增长 | 运行状态 |
| fifo_cnt | FIFO异常/占用 | 当前0 | 运行状态 |
| buf_empty_cnt | AO空buffer次数 | 空闲时会增长，只有播放期间才有诊断价值 |
| read/write | 通道读写帧数 | 播放时应匹配 |
| resample_open | AO重采样 | 当前关闭 |
| VQE | AO播放VQE | 当前关闭 |

提示音不响时应在提示音正在播放的瞬间采集AO；空闲快照的`buf_empty_cnt`不能单独判错。

## 26. `/proc/umap/acodec` 与 `/proc/umap/aio`

### 26.1 ACODEC

```sh
cat /proc/umap/acodec
```

| 字段组 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| i2s1_fs/i2s1_width | Codec采样率和位宽 | 16 kHz/16 bit | G音频属性 |
| mixer_left/right | ADC输入选择 | in0_diff/in1_diff | G:`mixer_mic_mode`经驱动转换 |
| adc/dac clk | ADC/DAC采样边沿 | fall | Codec驱动 |
| adc_hpf | ADC硬件高通 | Y | Codec驱动 |
| dac_deemph | DAC去加重 | none | Codec驱动 |
| power_state | Codec电源 | up | 运行状态 |
| gain_left/right | ADC增益 | 20/20 | `audiogain=40`经Codec映射 |
| boost_left/right | 麦克风增益提升 | 20/20 | 同上 |
| adc volume | ADC数字音量 | 0/0 | Codec驱动 |
| dac volume | DAC音量 | -8/-8 | G:`volume=68`经Codec映射 |
| mic/dac mute | 输入输出静音 | 全N | 运行状态 |
| pd_linein/adc/dac | 各模拟模块掉电 | 全N | 运行状态 |
| adc/dac select | 左右声道选择 | left/right | track mode/驱动 |

INI的`audiogain=40`不能与AI proc的`volume=0`直接比较；真正硬件输入增益应看ACODEC。

### 26.2 AIO

```sh
cat /proc/umap/aio
```

本机AIO节点存在但输出为空。它只是音频公共模块的proc入口，本版本没有额外表格。AI/AO正常工作时AIO为空不代表错误。

## 27. 辅助proc

### 27.1 `logmpp`

| 字段 | 用途 | 错误判断 | INI对应 |
|---|---|---|---|
| max_len/read/write/butt_pos | MPP日志环形buffer状态 | 写位置异常或buffer问题供底层诊断 | `/proc/cmdline logmpp_show=1` |
| 各模块level | SYS、VI、VENC等日志等级 | 实测均为3 | 运行/模块参数，不是媒体INI |

### 27.2 `ive`

| 字段组 | 用途 | 错误判断 |
|---|---|---|
| save_power/max_node_num | IVE省电和最大节点 | 驱动能力 |
| wait/busy队列 | IVE任务队列 | 当前均0 |
| task_finish/task_id | 任务完成状态 | 当前无任务 |
| total_int/runtime | 中断和运行统计 | 当前0 |
| dma/filter/csc/sobel等 | 每种IVE算子调用次数 | 当前全0 |
| utili | IVE利用率 | 当前0 |

当前业务没有创建IVE任务。无媒体INI直接对应。

### 27.3 `md`

MD节点只有表头、没有通道行，表示运动检测驱动已加载但当前HC112没有创建MD通道。无当前媒体INI对应。

### 27.4 `svp_npu`

| 字段组 | 用途 | 错误判断 |
|---|---|---|
| save_power/task/stream/event上限 | NPU驱动资源能力 | 静态能力 |
| free_model/stream/report | 空闲资源 | 当前全部空闲 |
| irq计数 | NPU中断 | 当前0 |
| hw_status/utilization | 硬件状态和利用率 | 当前0 |
| timeout_err/hw_err/aicpu_err | NPU错误 | 应为0 |
| task time/cycle | 推理任务耗时 | 当前无任务 |

当前配置没有NPU媒体业务，节点存在不代表AI算法已启用。

### 27.5 `pm`

| 字段 | 用途 | HC112实测 | INI对应 |
|---|---|---|---|
| tcomp/pacomp enable | 温度/工艺补偿开关 | core温补开启 | 电源驱动 |
| temp/pa comp | 电压补偿值 | 动态 | 电源驱动 |
| cur_temp | 芯片温度 | 约53℃ | 无 |
| core/cpu/npu volt | 当前电压 | core约892 mV | 无 |

温度应观察长期趋势。单次53℃正常与否还需结合环境温度、外壳和负载，不能仅凭proc一个点下结论。

## 28. PROC与INI对应关系总表

| proc | 直接对应INI | 间接/转换对应 | 没有INI对应的主要内容 |
|---|---|---|---|
| sys | Bind配置 | PARAM/MAPI创建结果 | 版本、状态、计数、缩放系数 |
| mipi_rx | 输入类型、RAW10、尺寸、WDR | Sensor驱动 | lane状态、PHY频率、错误计数 |
| isp | 尺寸、帧率、WDR、镜像 | Scene参数S | 曝光/AWB实时值、耗时、错误计数 |
| vi | M/C的Dev、Pipe、Chn参数 | 枚举和运行模式转换 | 中断、发送、丢帧、性能 |
| vpss | M/C的Grp和Vport参数 | 压缩/对齐/驱动选择 | 处理计数、负载、错误 |
| venc | M/C/G的通道属性 | 代码设置fast-enc等 | started、sequence、队列和错误 |
| h265e/h264e | profile、参考帧、帧内刷新 | 代码高级参数 | 编码计数、buffer、错误 |
| rc | 码率、fps、GOP、QP、QVBR | 代码设置NORMALP/recode | 瞬时码率、运行QP、丢帧 |
| jpege | 尺寸、buffer、qfactor、DCF | 单拍启动/停止 | 成功、丢图和buffer状态 |
| chnl | 无直接项 | VENC通道创建结果 | 调度器、VPU错误和耗时 |
| vb | Pool size/count | 驱动对齐 | owner、free、min_free |
| media-mem | MMZ启动参数 | VB/VENC等分配结果 | 地址、pid、实时用量 |
| rgn | W中的OSD和display | 坐标缩放、bitmap生成 | canvas、地址、VGS计数 |
| vgs | 无 | VPSS/RGN内部调用 | job/task/硬件错误 |
| ai | G的AI格式和VQE开关 | ACODEC映射 | DMA、中断、队列、错误 |
| ab | 无直接项 | AI帧规格计算 | Audio Block占用 |
| aenc | G的AAC通道和点数 | AAC插件/MAPI | 编码计数和错误 |
| adec | 无 | 提示音播放代码 | 解码计数 |
| ao | G的AO格式和音量 | ACODEC映射 | 中断、buffer和播放计数 |
| acodec | 音频格式/增益/音量 | Codec ioctl转换 | 模拟寄存器状态、电源 |
| aio | 无 | 音频公共模块 | 当前无输出 |
| logmpp | 启动参数 | 模块日志初始化 | 日志buffer和等级 |
| ive/md/npu | 当前无业务INI | 驱动加载 | 资源、任务和错误 |
| pm | 无 | 电源驱动 | 温度、电压、补偿 |

## 29. 初学者排查顺序

### 29.1 没有视频

```text
mipi_rx错误
→ ISP中断和帧率
→ VI send/lost/vb_fail
→ VPSS send_ok/error
→ VENC started和送帧错误
→ H26x成功/丢帧
→ 消费者get/release
```

### 29.2 录像正常但APP副码流没有画面

```text
SYS中VPSS0/1→VENC1 Bind
→ VPSS ch1 send_ok
→ VENC1 started
→ H264E enc_succeed
→ RC inst_fr/inst_br
→ VENC stream user_get/release
```

S1已经证明当前副码流活动时为1024×576@25 fps、约2 Mbps。

### 29.3 APP拍照失败

```text
VENC2 sequence/PTS
→ JPEGE错误字段
→ VPSS0/0是否正常
→ VB free/min_free
→ RGN绑定VENC2
→ APP回调和文件保存日志
```

不要只看抓拍结束后的JPEGE累计值，因为当前驱动会清理单拍流buffer。

### 29.4 有声音问题

录像无声：

```text
AI user_get/release
→ AB free/min_free
→ AENC recv/enc/get/release
→ TS/RTSP消费者
```

提示音不响：

```text
ADEC send/get/put
→ AO播放瞬间read/write
→ ACODEC mute/power/DAC volume
```

## 30. 当前实测结论

1. 默认媒体规格是3840×2160@25 fps，不是30 fps；
2. Sensor→MIPI→ISP→VI→VPSS主链正常，MIPI和主要视频错误计数为0；
3. VENC0为4K25 H.265 QVBR 22528 kbps；
4. VENC1为1024×576@25 H.264 CBR 2048 kbps；
5. VENC2为4K JPEG，VENC3为320×180 JPEG缩略图，qfactor均为95；
6. 拍照必须通过APP，因此实际并发包含主、副RTSP；
7. AI→AENC为16 kHz、16 bit、mono、AAC-LC 48 kbps、1024点/帧；
8. VB的两个Block size与INI略有差异是驱动对齐，不是INI未生效；
9. 目前关键MIPI、VI、VPSS、VENC、H26x、音频错误字段没有显示持续故障；
10. proc中只有配置类字段能和INI对应，计数器、地址、耗时、温度和大部分错误字段本来就没有INI对应。
