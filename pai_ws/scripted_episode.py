#!/usr/bin/env python3
# 台本どおりの軌道で CRANE+ V2 を動かす（テレオペの代わり）。収録側は無変更。
import argparse, time
import rclpy
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

ARM_JOINTS = ['crane_plus_joint1', 'crane_plus_joint2', 'crane_plus_joint4', 'crane_plus_joint3']
GRIPPER_JOINT = 'crane_plus_joint_hand'
OPEN, CLOSE = -0.5236, 0.1745   # 開-30°, 閉+10°
HZ = 20
HOME = [0.0, 0.0, 0.0, 0.0]

# ([joint1, joint2, joint4, joint3], gripper(0=開/1=閉), 秒)
WAYPOINTS = [
    ([0.0,   0.0,   0.0,    0.0  ], 0, 1.0),   # 初期化: 直立でホールド
    ([0.0,   0.8,   0.0,    0.0  ], 0, 1.5),   # お辞儀
    ([0.0,   0.8,   0.0,    0.0  ], 0, 0.8),   # 保持
    ([0.0,   0.0,   0.0,    0.0  ], 0, 1.2),   # 起こす
    ([0.5,   0.2,   0.0,    0.0  ], 0, 0.8),   # 手振り 左（開）
    ([-0.5,  0.2,   0.0,    0.0  ], 1, 1.2),   # 手振り 右（閉）
    ([0.0,   0.2,   0.0,    0.0  ], 0, 0.8),   # 中央（開）
    ([-1.40, 0.04, -1.35,  -1.65 ], 0, 2.5),   # ブロックの真上へ
    ([-1.40, 0.24, -0.70,  -2.10 ], 0, 0.7),   # 下ろす1
    ([-1.40, 0.48, -0.50,  -2.06 ], 0, 0.7),   # 下ろす2
    ([-1.40, 0.86, -0.16,  -2.02 ], 1, 0.7),   # 把持（深く・閉）
    ([-1.40,-0.04, -1.50,  -1.175], 1, 1.5),   # 持ち上げ
    ([-0.4, -0.04, -1.50,  -1.175], 1, 2.0),   # 差し出す
    ([-0.4, -0.04, -1.50,  -1.175], 1, 1.5),   # 保持
]

def gval(c):
    return CLOSE if c else OPEN

class Demo(Node):
    def __init__(self):
        super().__init__('scripted_demo')
        self.ap = self.create_publisher(JointTrajectory, '/crane_plus_arm_controller/joint_trajectory', 10)
        self.gp = self.create_publisher(JointTrajectory, '/crane_plus_gripper_controller/joint_trajectory', 10)
        self.arm = list(HOME)
        self.grip = OPEN
    def _pub(self):
        jt = JointTrajectory(); jt.joint_names = ARM_JOINTS
        p = JointTrajectoryPoint(); p.positions = list(self.arm); p.time_from_start.nanosec = 100000000
        jt.points = [p]; self.ap.publish(jt)
        jg = JointTrajectory(); jg.joint_names = [GRIPPER_JOINT]
        q = JointTrajectoryPoint(); q.positions = [float(self.grip)]; q.time_from_start.nanosec = 100000000
        jg.points = [q]; self.gp.publish(jg)
    def _goto(self, tgt, closed, dur):
        pa, pg = list(self.arm), self.grip
        tg = gval(closed); n = max(1, int(dur * HZ))
        for i in range(1, n + 1):
            a = i / n
            self.arm = [x + (y - x) * a for x, y in zip(pa, tgt)]
            self.grip = pg + (tg - pg) * a
            self._pub(); time.sleep(1.0 / HZ)
    def episode(self):
        for tgt, closed, dur in WAYPOINTS:
            self._goto(tgt, closed, dur)
    def home(self, dur=1.5):
        self._goto(HOME, 0, dur)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--loops', type=int, default=1)
    ap.add_argument('--pause', type=float, default=2.0)
    ap.add_argument('--home', action='store_true', help='直立に戻して終了（記録前の初期化用）')
    a = ap.parse_args()
    rclpy.init(); d = Demo()
    if a.home:
        print('homing...', flush=True); d.home(1.5)
    else:
        for k in range(a.loops):
            print(f'--- episode {k+1}/{a.loops} ---', flush=True)
            d.episode()
            if k + 1 < a.loops:
                time.sleep(a.pause)
    d.destroy_node(); rclpy.shutdown()

if __name__ == '__main__':
    main()
