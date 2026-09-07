# Bluetooth SIG Mesh 真实协议栈说明

> 本文说明 **Bluetooth SIG 标准 Mesh**（Bluetooth Mesh Profile / Mesh Protocol）的真实协议栈结构与关键流程。  
> 对比仓库中 `mesh_demo/`：那是教学用简化模型，**不是**可上芯片运行的 SIG 协议栈。

参考仓库分支：[InfinitePersistence/supreme-octo-meme @ mesh](https://github.com/InfinitePersistence/supreme-octo-meme/tree/mesh)

---

## 1. 总览：真实 Mesh 是什么

Bluetooth Mesh 由蓝牙技术联盟（Bluetooth SIG）标准化，建立在 **Bluetooth Low Energy（BLE）** 之上，面向多对多、大节点规模的设备控制（照明、楼宇、传感器等）。

与经典 BLE「连接导向、中心-外设」不同，Mesh 主要使用：

- **Advertising Bearer**：用 BLE 广播信道传 Mesh PDU（Managed Flooding）
- **GATT Bearer**：手机等不具备广播 Mesh 能力的设备，通过 **Proxy** 节点经 GATT 接入网络

核心思路：**已配网节点共享网络密钥，消息可经中继多跳扩散，并用 TTL / 缓存去重控制洪泛。**

---

## 2. 协议栈分层（真实 SIG 结构）

真实栈自下而上大致如下（厂商 SDK 命名可能略有差异，逻辑层一致）：

```
┌─────────────────────────────────────────┐
│  Models（模型层）                         │  应用语义：OnOff、Lightness、Vendor Model…
│  - Server / Client / Control             │
├─────────────────────────────────────────┤
│  Access Layer（访问层）                   │  应用数据 + AID/应用密钥选择、发布/订阅
├─────────────────────────────────────────┤
│  Upper Transport（上层传输）               │  Access 消息分段/重组、Friend Poll 等
│  Lower Transport（下层传输）              │  段传输、SAR、控制消息（Friend/Heartbeat）
├─────────────────────────────────────────┤
│  Network Layer（网络层）                  │  地址、TTL、NetKey 加解密、中继判定
├─────────────────────────────────────────┤
│  Bearer Layer（承载层）                   │  Advertising Bearer / GATT Bearer
├─────────────────────────────────────────┤
│  BLE 控制器 / Host（Link Layer 等）       │  广播、扫描、GATT、连接
└─────────────────────────────────────────┘
```

### 2.1 Bearer Layer（承载层）

| Bearer | 作用 |
|--------|------|
| **Advertising Bearer** | 用非连接 BLE 广播收发 Mesh 报文；节点之间的主干路径 |
| **GATT Bearer** | Proxy 节点提供 Mesh Proxy Service；手机 App 经连接收发 Mesh PDU |

真实栈必须处理：广播间隔、扫描窗口、Proxy Filter（白名单/黑名单减少手机侧流量）等。

### 2.2 Network Layer（网络层）

负责：

- **NetKey / NID**：标识网络，解密 Network PDU
- **SRC / DST 地址**：单播、组播、虚拟地址、广播地址
- **TTL**：每中继一次递减，防止无限转发
- **SEQ / IV Index**：抗重放；与序列号空间、IV Update 流程相关
- **Relay / Proxy / Friend 特性位**：决定本节点是否转发、是否代理、是否为 Friend

输出给下层的是加密后的 Network PDU；中继节点在本层解密（用 NetKey）后决定是否再加密发出。

### 2.3 Transport Layer（传输层）

分上下两层：

- **Lower Transport**
  - 把过长 Access 载荷 **分段（Segmentation）** 与重组
  - 传输控制 PDU：Friend Request/Offer/Poll/Update、Heartbeat 等
- **Upper Transport**
  - 应用层消息的端到端加密（**AppKey** 或 Device Key）
  - 与 Access 层对接「哪条消息用哪把应用密钥」

### 2.4 Access Layer（访问层）

- 定义 **Opcode + Parameters** 的应用 PDU 格式
- 绑定 **Model ↔ AppKey**
- 处理 **Publish / Subscribe**（发布地址、订阅列表）

### 2.5 Models（模型层）

SIG 定义了大量标准模型，例如：

- **Foundation Models**：Configuration Server/Client、Health Server/Client（配网后配置、心跳/故障）
- **Generic Models**：Generic OnOff、Level、Battery…
- **Lighting Models**：Lightness、CTL、HSL、LC…
- **Sensor / Time / Scene** 等
- **Vendor Model**：厂商自定义 Opcode（需公司 ID）

应用开发通常主要写 **Model 回调与状态机**；下面各层由芯片厂 Mesh SDK 提供。

---

## 3. 地址、密钥与安全

### 3.1 地址类型

| 类型 | 含义（概念） |
|------|----------------|
| Unicast | 每个元素（Element）一个唯一地址，配网时分配 |
| Group | 组播，多节点订阅同一组地址 |
| Virtual | 基于 Label UUID 的虚拟地址 |
| Fixed Group | 如所有代理、所有好友、所有中继、所有节点等固定组 |

一个节点可有多个 **Element**（多元素设备），各有单播地址。

### 3.2 密钥层次

| 密钥 | 作用 |
|------|------|
| **NetKey** | 网络层加解密、身份混淆相关材料派生 |
| **AppKey** | 绑定到某 NetKey；加密 Access 载荷，实现应用隔离 |
| **Device Key** | 每设备一把，主要用于 Configuration 模型（配网后配置） |
| **Network Key 派生键** | 如用于隐私的 Privacy Key、用于加密的 Encryption Key 等（由 NetKey 派生） |

没有正确密钥的节点无法解密，也就无法有效中继/处理（与教学 demo 里只比 `net_key_id` 不同，真实是 AES-CCM 等密码学操作）。

### 3.3 安全机制要点

- 加密与认证（防篡改）
- 序列号 + IV Index 抗重放
- 可选 **Privacy**（混淆源地址等字段）
- 配网过程本身也有安全流程（见下节）
- Mesh 1.1 等后续规范还增强了远程配网、定向转发（Directed Forwarding）等能力

---

## 4. 配网（Provisioning）真实流程

教学 demo 里「写入 net_key_id」只是示意。真实 Provisioning 大致阶段：

1. **Beacon / 发现**：未配网设备发 Unprovisioned Device Beacon（或通过 GATT）
2. **Invitation / Capability 交换**：Provisioner 与设备协商算法、公钥方式、注意力定时等
3. **公钥交换 / 认证**：OOB（输出/输入/静态）或 No OOB；防中间人
4. **分发 Provisioning Data**：NetKey、Key Index、Flags、IV Index、Unicast Address 等
5. **设备成为 Node**：关闭未配网信标，开始作为 Mesh 节点工作
6. **后续 Configuration**：用 Device Key 通过 Config Model 添加 AppKey、订阅组地址、设置 Publish、打开 Relay/Friend/Proxy 等

配网承载可以是：

- **PB-ADV**：广播配网
- **PB-GATT**：手机连设备 GATT 配网（很常见）

Mesh 1.1 还支持 **Remote Provisioning（RPR）**：经已有网络远程给远处设备配网。

---

## 5. 节点特性（Features）

| Feature | 真实行为 |
|---------|----------|
| **Relay** | 解密 Network PDU 后，若 TTL 允许且策略允许，再加密发出（Managed Flood） |
| **Proxy** | 提供 GATT Proxy，桥接手机 ↔ Mesh |
| **Friend** | 为 LPN 缓存消息，响应 Friend Poll |
| **Low Power（LPN）** | 长期休眠；与 Friend 建立 Friendship，周期性 Poll 取信 |

可选增强（视规范版本与 SDK）：

- **Heartbeat**：周期上报存活与跳数特征
- **Directed Forwarding**（Mesh 1.1）：减少盲目洪泛
- **Subnet Bridging** 等

---

## 6. 消息路径（一次 OnOff 如何走完栈）

以「手机经 Proxy 开灯」为例：

```
App (Generic OnOff Client Model)
  → Access：组 OnOff Set PDU，选 AppKey
  → Upper Transport：加密 Access 载荷
  → Lower Transport：必要时分段
  → Network：加 NetKey 保护，填 SRC/DST/TTL/SEQ
  → GATT Bearer：发到 Proxy 节点
Proxy 节点
  → 转入 Advertising Bearer，向周围广播
Relay 节点们
  → Network 层决定是否中继（TTL--，去重缓存）
灯节点（OnOff Server）
  → Network 解密成功且 DST 匹配（单播或组）
  → Transport / Access 解密成功
  → Model 改状态并可选 Status 回传
```

这与 `mesh_demo` 里「字符串 payload + 整数 net_key_id + 简单邻居洪泛」是同一故事的**高度缩略版**。

---

## 7. 与 `mesh_demo` 的对照

| 概念 | `mesh_demo`（教学） | SIG 真实栈 |
|------|---------------------|------------|
| 密钥 | `net_key_id` 整数比较 | NetKey / AppKey / DevKey + AES-CCM |
| 中继 | 邻居表 + TTL + (src,seq) 去重 | Network Cache、TTL、Relay 策略、隐私字段 |
| 配网 | 直接改角色与 key id | 完整 Provisioning + Config Model |
| 模型 | `MessageType` 枚举 | SIG/Vendor Model + Opcode |
| Bearer | 抽象 `neighbors` | ADV / GATT Bearer + Proxy Protocol |
| LPN | Friend 列表缓存 + poll | Friendship 状态机、Poll Timeout、缓存队列 |
| 实现位置 | 纯 Python 模拟 | 芯片厂 SDK（如泰凌 SIG Mesh SDK）+ 认证协议栈 |

**结论**：要在 TLSR825x 等芯片上跑真实 Mesh，应使用厂商 **SIG Mesh SDK**（协议栈已实现 Network/Transport/Access/Foundation），应用侧主要开发 **Model 与板级驱动**；`mesh_demo` 只适合理解角色与数据流。

---

## 8. 典型厂商 SDK 里你看得到的工程形态

以泰凌等厂商 SIG Mesh SDK 为例（名称因版本而异），常见镜像/工程角色：

- **mesh 节点**：灯/开关，含 Relay/Proxy/Friend 等编译选项
- **mesh_LPN**：低功耗节点
- **mesh_gw / provisioner**：网关与配网
- **master dongle + PC 工具**：GATT Provisioner 调试
- **Vendor Model 钩子**：自定义 Opcode 处理

开发者工作重点通常是：

1. 选对芯片与 SDK 分支（825x / 827x / 9 系）
2. 配置 Composition Data（几个 Element、哪些 Model）
3. 实现 Server 状态与 Client 控制逻辑
4. 配网、绑定 AppKey、订阅组地址
5. 功耗、Relay 密度、GATT Proxy、OTA 等产品化问题

---

## 9. 规范与学习路径（建议）

1. Bluetooth SIG 公布的 **Mesh Protocol / Mesh Profile** 规范（含 Mesh 1.0 / 1.1 更新）
2. 官方模型规范（Generic / Lighting / Sensor…）
3. 芯片厂 **SIG Mesh SDK 开发手册** + 例程（灯、网关、LPN）
4. 用 Proxy App 或厂商工具完成一次真实配网与组控，对照抓包/日志看 PDU

---

## 10. 小结

SIG 真实协议栈是一套 **分层、加密、可认证** 的完整体系：

**BLE Bearer → Network → Transport → Access → Models**

再叠加 **Provisioning、Configuration、Relay/Proxy/Friend/LPN** 等机制。  
仓库中的 `mesh_demo` 用可读的 Python 演示了「配网 / 多跳 / 广播 / Friend-LPN」直觉；要落地产品，请转到 **Bluetooth SIG 规范 + 芯片厂 SIG Mesh SDK**。
