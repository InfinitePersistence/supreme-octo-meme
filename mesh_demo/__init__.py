# -*- coding: utf-8 -*-
"""mesh_demo 包初始化：导出常用符号，方便外部 import。"""

from mesh_network import ADDR_ALL, ADDR_RELAY_GROUP, MeshNetwork  # 导出网络相关
from mesh_node import MeshMessage, MeshNode, MessageType, NodeRole  # 导出节点与消息相关

__all__ = [  # 明确公开接口列表
    "ADDR_ALL",  # 广播地址
    "ADDR_RELAY_GROUP",  # 中继组地址
    "MeshNetwork",  # 网络类
    "MeshMessage",  # 消息类
    "MeshNode",  # 节点类
    "MessageType",  # 消息类型枚举
    "NodeRole",  # 节点角色枚举
]
