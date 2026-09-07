# -*- coding: utf-8 -*-
"""蓝牙 Mesh 网络层：配网、广播中继、Friend 缓存（教学简化实现）。"""

from __future__ import annotations  # 允许前向引用类型

from typing import Dict, List, Optional  # 类型注解

from mesh_node import MeshMessage, MeshNode, MessageType, NodeRole  # 导入节点与消息定义


# 广播地址约定（仅本教学工程使用，非 SIG 官方地址分配）
ADDR_ALL = 0xFFFF  # 全网广播
ADDR_RELAY_GROUP = 0xC000  # “所有中继”组播示例


class MeshNetwork:
    """模拟一整张 Mesh 网：节点表 + 射频邻居关系 + 消息洪泛。"""

    def __init__(self, net_key_id: int = 1) -> None:
        """创建空网络，并指定本网的 NetKey 编号。"""
        self.net_key_id = net_key_id  # 网络密钥标识（真实场景是 128-bit 密钥）
        self.nodes: Dict[int, MeshNode] = {}  # 地址 -> 节点
        self._next_unicast = 0x0001  # 下一个可分配的单播地址
        self.provisioner: Optional[MeshNode] = None  # 当前配网器节点

    def add_node(self, node: MeshNode) -> None:
        """把节点登记进网络对象（尚未等于已配网）。"""
        if node.address in self.nodes:  # 地址冲突检查
            raise ValueError(f"地址 {node.address:04X} 已存在")  # 抛出错误
        self.nodes[node.address] = node  # 登记节点
        if NodeRole.PROVISIONER in node.roles:  # 若带配网器角色
            self.provisioner = node  # 记录为默认 Provisioner

    def link(self, a: int, b: int) -> None:
        """建立双向一跳邻居关系（模拟 RF 能互相听到）。"""
        if a not in self.nodes or b not in self.nodes:  # 两端都必须已登记
            raise KeyError("link 的两端节点必须先 add_node")  # 提示调用顺序
        self.nodes[a].neighbors.add(b)  # a 能听到 b
        self.nodes[b].neighbors.add(a)  # b 能听到 a

    def allocate_address(self) -> int:
        """分配一个未使用的单播地址。"""
        while self._next_unicast in self.nodes:  # 跳过已占用地址
            self._next_unicast += 1  # 继续往后找
        addr = self._next_unicast  # 取当前可用地址
        self._next_unicast += 1  # 指针后移，供下次使用
        return addr  # 返回分配结果

    def provision(self, node: MeshNode, roles: Optional[set] = None) -> None:
        """配网：把未配网节点加入本网络（简化版 Provisioning）。"""
        if self.provisioner is None:  # 没有配网器就无法配网
            raise RuntimeError("网络中还没有 Provisioner")  # 报错
        if not self.provisioner.is_provisioned() and self.provisioner.net_key_id is None:  # 配网器自己也要有密钥
            self.provisioner.net_key_id = self.net_key_id  # 给配网器写入 NetKey
            self.provisioner.roles.discard(NodeRole.UNPROVISIONED)  # 去掉未配网标记
            self.provisioner.roles.add(NodeRole.PROVISIONER)  # 确保有配网角色
            self.provisioner.roles.add(NodeRole.RELAY)  # 教学里让配网器兼中继
            self.provisioner.roles.add(NodeRole.PROXY)  # 并标记可代理手机接入
        node.net_key_id = self.net_key_id  # 给目标节点下发同一 NetKey 编号
        node.roles.discard(NodeRole.UNPROVISIONED)  # 节点离开未配网状态
        if roles:  # 若调用方指定了角色集合
            node.roles |= set(roles)  # 合并进节点角色
        else:  # 默认角色
            node.roles.add(NodeRole.RELAY)  # 默认成为普通中继节点
        print(  # 打印配网成功日志
            f"[配网] {self.provisioner.name} 将 {node.name}@{node.address:04X} "
            f"加入网络 NetKey={self.net_key_id}，角色={[r.name for r in node.roles]}"
        )

    def send(self, src: MeshNode, msg: MeshMessage) -> None:
        """从源节点发出消息，进入网络洪泛。"""
        if not src.is_provisioned():  # 未配网节点不能发网内消息
            raise RuntimeError(f"{src.name} 尚未配网，不能发送")  # 报错
        if msg.net_key_id != self.net_key_id:  # 密钥不一致视为无法解密
            raise RuntimeError("NetKey 不匹配，丢弃发送")  # 报错
        print(  # 发送日志
            f"[发送] {src.name}@{src.address:04X} -> {msg.dst:04X} "
            f"type={msg.msg_type.name} ttl={msg.ttl} seq={msg.seq} payload={msg.payload!r}"
        )
        src.remember(msg)  # 源节点自己先记入去重表，避免环回重复处理
        self._flood(from_addr=src.address, msg=msg)  # 向邻居洪泛

    def _flood(self, from_addr: int, msg: MeshMessage) -> None:
        """向 from_addr 的邻居广播一帧（带 TTL 与去重的简化中继）。"""
        sender = self.nodes[from_addr]  # 取出当前发送/转发节点
        for nb_addr in list(sender.neighbors):  # 遍历一跳邻居
            nb = self.nodes[nb_addr]  # 取邻居节点对象
            self._receive(nb, msg)  # 邻居“听到”该广播帧

    def _receive(self, node: MeshNode, msg: MeshMessage) -> None:
        """节点收到一帧广播后的处理：去重、本机交付、中继。"""
        if node.net_key_id != msg.net_key_id:  # 不同网络的包解不开
            return  # 静默丢弃
        if not node.remember(msg):  # 若是重复包
            return  # 去重丢弃，防止广播风暴
        # LPN 多数时间休眠：空中听到也不在本地立即处理，改由 Friend 缓存后 poll 取回
        is_lpn_only = NodeRole.LPN in node.roles and NodeRole.FRIEND not in node.roles  # 是否为纯低功耗节点
        if node.accept_for_self(msg) and not is_lpn_only:  # 普通节点且是目的地则本地处理
            node.handle_local(msg)  # 应用层处理
        # Friend 缓存：发给 LPN 的单播，或广播，都由 Friend 帮忙存一份
        if NodeRole.FRIEND in node.roles:  # 本节点具备 Friend 能力
            target = self.nodes.get(msg.dst)  # 查单播目的节点
            for_lpn_unicast = target is not None and NodeRole.LPN in target.roles  # 单播目标是 LPN
            for_broadcast = msg.dst == ADDR_ALL  # 广播也可能要给休眠 LPN
            if for_lpn_unicast or for_broadcast:  # 需要帮 LPN 留存
                # 广播时缓存给所有已关联 LPN：教学里简化为“只要是 Friend 就存”
                node.friend_cache.append(msg)  # 写入 Friend 队列
                tip = target.name if for_lpn_unicast else "广播接收者"  # 日志里的对象名
                print(f"[Friend] {node.name} 为 LPN({tip}) 缓存 seq={msg.seq}")  # 打印缓存日志
        # 中继：TTL>1 且本节点可中继时，TTL-1 后继续洪泛
        if msg.ttl <= 1:  # TTL 耗尽
            return  # 不再转发
        if not node.can_relay():  # 无中继能力（例如纯 LPN）
            return  # 不转发
        relayed = MeshMessage(  # 构造转发副本（真实协议还会改一些头字段）
            src=msg.src,  # 源地址保持不变（端到端语义）
            dst=msg.dst,  # 目的保持不变
            msg_type=msg.msg_type,  # 类型不变
            payload=msg.payload,  # 载荷不变
            ttl=msg.ttl - 1,  # TTL 减一
            seq=msg.seq,  # 序列号不变，便于全网去重
            net_key_id=msg.net_key_id,  # 仍属同一网络
        )
        print(  # 中继日志
            f"[中继] {node.name}@{node.address:04X} 转发 "
            f"{relayed.src:04X}->{relayed.dst:04X} ttl={relayed.ttl}"
        )
        self._flood(from_addr=node.address, msg=relayed)  # 继续向邻居扩散

    def lpn_poll_friend(self, lpn: MeshNode, friend: MeshNode) -> List[MeshMessage]:
        """LPN 向 Friend 取回缓存消息（简化 Friendship 轮询）。"""
        if NodeRole.LPN not in lpn.roles:  # 调用方必须是 LPN
            raise RuntimeError("只有 LPN 才能 poll Friend")  # 报错
        if NodeRole.FRIEND not in friend.roles:  # 对方必须是 Friend
            raise RuntimeError("目标不是 Friend 节点")  # 报错
        delivered: List[MeshMessage] = []  # 收集取回的消息
        remain: List[MeshMessage] = []  # 不属于该 LPN 的继续留着
        for m in friend.friend_cache:  # 遍历缓存
            if m.dst == lpn.address or m.dst == ADDR_ALL:  # 发给该 LPN 或广播
                lpn.handle_local(m)  # 交给 LPN 应用层
                delivered.append(m)  # 记入已交付列表
            else:  # 其它目的
                remain.append(m)  # 继续缓存
        friend.friend_cache = remain  # 写回剩余缓存
        print(f"[LPN Poll] {lpn.name} 从 {friend.name} 取回 {len(delivered)} 条消息")  # 日志
        return delivered  # 返回取回结果

    def snapshot(self) -> None:
        """打印当前网络拓扑与节点状态，便于观察。"""
        print("========== Mesh 网络快照 ==========")  # 标题
        for addr in sorted(self.nodes):  # 按地址排序打印
            n = self.nodes[addr]  # 取节点
            roles = ",".join(sorted(r.name for r in n.roles)) or "-"  # 角色字符串
            nbs = ",".join(f"{x:04X}" for x in sorted(n.neighbors)) or "-"  # 邻居列表
            print(  # 一行节点信息
                f"  {n.name:10s} addr={addr:04X} provisioned={n.is_provisioned()} "
                f"on={n.state_on} roles=[{roles}] neighbors=[{nbs}]"
            )
        print("===================================")  # 结束线
