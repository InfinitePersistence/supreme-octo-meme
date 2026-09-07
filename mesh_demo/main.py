# -*- coding: utf-8 -*-
"""Mesh 演示入口：搭一个小拓扑，完成配网、开关控制、中继与 LPN 取信。"""

from mesh_network import ADDR_ALL, MeshNetwork  # 导入网络类与广播地址
from mesh_node import MeshNode, MessageType, NodeRole  # 导入节点、消息类型、角色


def build_demo_network() -> MeshNetwork:
    """搭建教学拓扑：手机式配网器 -- 网关中继 -- 两盏灯，另加 Friend/LPN。"""
    net = MeshNetwork(net_key_id=0x11)  # 创建网络，NetKey 编号设为 0x11

    # 地址在教学里预先固定，方便对照日志（真实由 Provisioner 动态分配）
    phone = MeshNode(  # 模拟手机 / Provisioner
        address=0x0001,  # 单播地址 0x0001
        name="Phone",  # 名称
        roles={NodeRole.PROVISIONER, NodeRole.UNPROVISIONED},  # 初始带配网器意图，尚未真正入网
    )
    gateway = MeshNode(  # 网关 / 强中继 / Friend
        address=0x0002,  # 地址 0x0002
        name="Gateway",  # 名称
        roles={NodeRole.UNPROVISIONED},  # 出厂未配网
    )
    light_a = MeshNode(  # 灯 A
        address=0x0010,  # 地址 0x0010
        name="LightA",  # 名称
        roles={NodeRole.UNPROVISIONED},  # 未配网
    )
    light_b = MeshNode(  # 灯 B（故意不与 Phone 直连，靠中继到达）
        address=0x0011,  # 地址 0x0011
        name="LightB",  # 名称
        roles={NodeRole.UNPROVISIONED},  # 未配网
    )
    sensor = MeshNode(  # 低功耗传感器 LPN
        address=0x0020,  # 地址 0x0020
        name="SensorLPN",  # 名称
        roles={NodeRole.UNPROVISIONED},  # 未配网
    )

    net.add_node(phone)  # 登记手机
    net.add_node(gateway)  # 登记网关
    net.add_node(light_a)  # 登记灯 A
    net.add_node(light_b)  # 登记灯 B
    net.add_node(sensor)  # 登记传感器

    # 拓扑：Phone <-> Gateway <-> LightA
    #                 |          \
    #                 +-> LightB  +-> SensorLPN
    # Phone 听不到 LightB，必须经 Gateway 中继，用来证明 Mesh 多跳
    net.link(0x0001, 0x0002)  # Phone 连 Gateway
    net.link(0x0002, 0x0010)  # Gateway 连 LightA
    net.link(0x0002, 0x0011)  # Gateway 连 LightB
    net.link(0x0010, 0x0020)  # LightA 连 Sensor（传感器靠近灯 A）

    return net  # 返回搭好的网络


def run_demo() -> None:
    """跑一遍完整演示流程。"""
    net = build_demo_network()  # 构建拓扑
    phone = net.nodes[0x0001]  # 取出手机节点
    gateway = net.nodes[0x0002]  # 取出网关
    light_a = net.nodes[0x0010]  # 取出灯 A
    light_b = net.nodes[0x0011]  # 取出灯 B
    sensor = net.nodes[0x0020]  # 取出传感器

    print("\n>>> 1) 配网：Provisioner 把设备拉进同一 NetKey 网络")  # 步骤说明
    net.provision(phone, roles={NodeRole.PROVISIONER, NodeRole.PROXY, NodeRole.RELAY})  # 先让手机真正成为配网器
    net.provision(gateway, roles={NodeRole.RELAY, NodeRole.PROXY, NodeRole.FRIEND})  # 网关：中继+代理+Friend
    net.provision(light_a, roles={NodeRole.RELAY})  # 灯 A：可中继
    net.provision(light_b, roles={NodeRole.RELAY})  # 灯 B：可中继
    net.provision(sensor, roles={NodeRole.LPN})  # 传感器：低功耗节点，不做中继

    net.snapshot()  # 打印配网后快照

    print("\n>>> 2) 单播开灯：Phone -> LightB（必须经 Gateway 中继）")  # 步骤说明
    on_msg = phone.create_message(  # 手机构造开灯消息
        dst=light_b.address,  # 目的：灯 B
        msg_type=MessageType.ON_OFF,  # 开关类型
        payload="on",  # 打开
        ttl=5,  # 允许最多若干跳
    )
    net.send(phone, on_msg)  # 发出并洪泛

    print("\n>>> 3) 广播关灯：Phone -> ALL")  # 步骤说明
    off_msg = phone.create_message(  # 构造广播关灯
        dst=ADDR_ALL,  # 全网广播
        msg_type=MessageType.ON_OFF,  # 开关类型
        payload="off",  # 关闭
        ttl=5,  # TTL
    )
    net.send(phone, off_msg)  # 发送

    print("\n>>> 4) 给 LPN 发消息：先到 Friend(Gateway) 缓存，再由 LPN 轮询取回")  # 步骤说明
    # 为演示 Friend 路径：让 Gateway 也能“听到”发往传感器的包
    # 真实 Mesh 里 Friendship 有独立建立流程；这里用拓扑+缓存近似
    net.link(0x0002, 0x0020)  # 补一条 Gateway-Sensor 邻接，方便 Friend 收到单播
    lpn_cmd = phone.create_message(  # 给传感器下发一条状态查询/通知
        dst=sensor.address,  # 目的 LPN
        msg_type=MessageType.STATUS,  # 状态类消息
        payload="temp-query",  # 载荷：温度查询
        ttl=5,  # TTL
    )
    net.send(phone, lpn_cmd)  # 发送；Gateway 作为 Friend 会缓存
    net.lpn_poll_friend(sensor, gateway)  # LPN 醒来向 Friend 取信

    print("\n>>> 5) 心跳：LightA 广播，观察中继扩散")  # 步骤说明
    hb = light_a.create_message(  # 灯 A 发心跳
        dst=ADDR_ALL,  # 广播
        msg_type=MessageType.HEARTBEAT,  # 心跳类型
        payload="alive",  # 存活载荷
        ttl=3,  # 较小 TTL
    )
    net.send(light_a, hb)  # 发送

    net.snapshot()  # 最终状态快照
    print("\n演示结束。")  # 结束提示


if __name__ == "__main__":  # 仅直接运行本文件时执行
    run_demo()  # 启动演示
