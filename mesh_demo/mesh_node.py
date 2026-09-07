# -*- coding: utf-8 -*-
"""蓝牙 Mesh 节点实现（教学用简化模型，非真实 SIG 协议栈）。"""

from __future__ import annotations  # 允许类型注解里使用尚未定义的类名

from dataclasses import dataclass, field  # 用数据类简化节点/消息结构定义
from enum import Enum, auto  # 用枚举表示节点角色与消息类型
from typing import Callable, Dict, List, Optional, Set  # 常用类型注解


class NodeRole(Enum):
    """节点在 Mesh 网络中的角色（对应真实 Mesh 的 Feature）。"""

    UNPROVISIONED = auto()  # 未配网：还不能进网通信
    RELAY = auto()  # 中继：可转发别人的消息，扩大覆盖
    PROXY = auto()  # 代理：可让手机经 GATT 接入 Mesh（此处仅标记）
    FRIEND = auto()  # Friend：帮低功耗节点缓存消息
    LPN = auto()  # Low Power Node：多数时间休眠，靠 Friend 收消息
    PROVISIONER = auto()  # 配网器：负责把未配网设备加入网络


class MessageType(Enum):
    """应用层消息类型（真实 Mesh 里对应 Model / Opcode）。"""

    ON_OFF = auto()  # 开关灯一类的控制指令
    STATUS = auto()  # 状态上报
    PROVISION = auto()  # 配网相关（本示例里单独走配网流程）
    HEARTBEAT = auto()  # 心跳，用于演示存活与可达性


@dataclass
class MeshMessage:
    """一帧 Mesh 消息（教学简化版）。"""

    src: int  # 源地址（unicast）
    dst: int  # 目的地址：单播、组播或广播地址
    msg_type: MessageType  # 消息类型
    payload: str  # 载荷（真实协议是二进制；这里用字符串方便演示）
    ttl: int = 5  # Time To Live：每中继一次减 1，防止无限转发
    seq: int = 0  # 序列号：配合 src 做去重
    net_key_id: int = 0  # 网络密钥标识（真实里是 NetKey；这里只存编号）


@dataclass
class MeshNode:
    """一个 Mesh 节点（灯、开关、传感器、网关等的抽象）。"""

    address: int  # 单播地址：配网后由 Provisioner 分配
    name: str  # 节点名称，便于打印日志
    roles: Set[NodeRole] = field(default_factory=set)  # 本节点具备的角色集合
    net_key_id: Optional[int] = None  # 已加入网络则持有 NetKey 编号，否则为 None
    neighbors: Set[int] = field(default_factory=set)  # 一跳邻居地址（模拟射频可达）
    seen: Set[tuple] = field(default_factory=set)  # 已见过的 (src, seq)，用于去重
    seq_counter: int = 0  # 本节点发出消息时递增的序列号
    state_on: bool = False  # 应用状态：例如灯是否点亮
    friend_cache: List[MeshMessage] = field(default_factory=list)  # Friend 为 LPN 缓存的消息
    on_deliver: Optional[Callable[["MeshNode", MeshMessage], None]] = None  # 消息送达本节点时的回调

    def is_provisioned(self) -> bool:
        """判断节点是否已配网。"""
        return self.net_key_id is not None and NodeRole.UNPROVISIONED not in self.roles  # 有密钥且不是未配网

    def can_relay(self) -> bool:
        """判断本节点是否允许做中继转发。"""
        return self.is_provisioned() and NodeRole.RELAY in self.roles  # 已入网且具备 RELAY 角色

    def next_seq(self) -> int:
        """生成本节点下一条消息的序列号。"""
        self.seq_counter += 1  # 序列号加一
        return self.seq_counter  # 返回新序列号

    def create_message(
        self,
        dst: int,
        msg_type: MessageType,
        payload: str,
        ttl: int = 5,
    ) -> MeshMessage:
        """构造一条由本节点发出的消息。"""
        return MeshMessage(  # 创建消息对象
            src=self.address,  # 源地址填自己
            dst=dst,  # 目的地址由调用方指定
            msg_type=msg_type,  # 消息类型
            payload=payload,  # 载荷内容
            ttl=ttl,  # 初始 TTL
            seq=self.next_seq(),  # 自动分配序列号
            net_key_id=self.net_key_id or 0,  # 使用本节点网络密钥编号
        )

    def accept_for_self(self, msg: MeshMessage) -> bool:
        """判断消息是否应被本节点作为“目的地”处理。"""
        if msg.dst == self.address:  # 单播给自己
            return True  # 接收
        if msg.dst == 0xFFFF:  # 约定 0xFFFF 为全网广播（教学用）
            return True  # 广播人人接收
        if msg.dst == 0xC000 and NodeRole.RELAY in self.roles:  # 约定 0xC000 为“所有中继组”
            return True  # 组播示例：中继节点也收
        return False  # 其它情况不作为本节点应用层消息

    def handle_local(self, msg: MeshMessage) -> None:
        """本节点应用层处理已送达的消息。"""
        if msg.msg_type == MessageType.ON_OFF:  # 开关指令
            self.state_on = msg.payload.strip().lower() in ("1", "on", "true")  # 解析开关
            print(f"[{self.name}@{self.address:04X}] 灯状态 -> {'开' if self.state_on else '关'}")  # 打印状态
        elif msg.msg_type == MessageType.STATUS:  # 状态类
            print(f"[{self.name}@{self.address:04X}] 收到状态: {msg.payload}")  # 打印载荷
        elif msg.msg_type == MessageType.HEARTBEAT:  # 心跳
            print(f"[{self.name}@{self.address:04X}] 心跳来自 {msg.src:04X}: {msg.payload}")  # 打印心跳
        else:  # 其它类型
            print(f"[{self.name}@{self.address:04X}] 收到 {msg.msg_type.name}: {msg.payload}")  # 通用打印
        if self.on_deliver is not None:  # 若设置了回调
            self.on_deliver(self, msg)  # 调用外部回调，便于测试挂钩

    def remember(self, msg: MeshMessage) -> bool:
        """记录消息指纹；若已见过则返回 False（应丢弃）。"""
        key = (msg.src, msg.seq)  # 用源地址+序列号做唯一键
        if key in self.seen:  # 已经处理或转发过
            return False  # 告诉调用方：这是重复包
        self.seen.add(key)  # 记入去重表
        return True  # 首次见到，可以继续处理
