#!/usr/bin/env python3
# 通しシーケンス: お辞儀 → 手振り → 把持 → 持ち上げ → 差し出し → 保持
#   挨拶は scripted_episode.py の WAYPOINTS を流用、把持以降は 2026-10-15 確定パラメータ
#
#   使い方:
#     python3 demo_full.py                     # 通し1本（高さ=low）
#     python3 demo_full.py --height mid        # 持ち上げ高さを変えて通し（low/mid/high/higher）
#     python3 demo_full.py --compare-heights   # ★高さ4案を順に試して保持できたか比較（挨拶なし・最短）
#     python3 demo_full.py --reset-only        # 箱を初期位置に戻すだけ
#     python3 demo_full.py --home              # 直立に戻すだけ
import argparse, re, subprocess, time
import rclpy
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from sensor_msgs.msg import JointState

ARM_JOINTS = ['crane_plus_joint1', 'crane_plus_joint2', 'crane_plus_joint4', 'crane_plus_joint3']
GRIPPER_JOINT = 'crane_plus_joint_hand'
HZ = 20
OPEN, CLOSE = -0.60, 0.6679
HOME = [0.0, 0.0, 0.0, 0.0]

ABOVE = [-1.571, -0.140, -1.700, -1.580]   # 箱の真上（固定）
DOWN  = [-1.571,  0.180, -1.100, -1.550]   # 下降＝把持姿勢（固定・実証済み）

# 持ち上げ高さの候補: (腕の形, 手先z, 真下向き度)
HEIGHTS = {
    'low':    [-1.571, -0.140, -1.700, -1.400],  # 手先1.153 / 0.98 ← 現状・実証済み
    'mid':    [-1.571, -0.220, -1.650, -1.350],  # 手先1.165 / 0.94
    'high':   [-1.571, -0.300, -1.600, -1.300],  # 手先1.178 / 0.86
    'higher': [-1.571, -0.400, -1.550, -1.200],  # 手先1.196 / 0.70（傾き大・落ちやすい）
}
CUBE = (-0.015, -0.140, 1.02)
CUBE_NAME = 'wood_cube_5cm'
Z_OK = 1.020          # これより高ければ「保持できている」

GREETING = [
    ('初期化(直立)',   HOME,                     False, 0.2),   # 静止を短く（動き出しを明確に）
    ('お辞儀',         [ 0.0,  0.8,  0.0,  0.0], False, 1.5),
    ('お辞儀ホールド',  [ 0.0,  0.8,  0.0,  0.0], False, 0.3),   # 静止を短く
    ('起こす',         [ 0.0,  0.0,  0.0,  0.0], False, 1.2),
    ('手振り左',       [ 0.5,  0.2,  0.0,  0.0], False, 0.8),
    ('手振り右',       [-0.5,  0.2,  0.0,  0.0], True,  1.2),
    ('中央',           [ 0.0,  0.2,  0.0,  0.0], False, 0.8),
]

def set_cube(x, y, z):
    req = ('name: "%s", position: {x: %f, y: %f, z: %f}, '
           'orientation: {x: 0, y: 0, z: 0, w: 1}') % (CUBE_NAME, x, y, z)
    subprocess.run(['ign', 'service', '-s', '/world/default/set_pose',
                    '--reqtype', 'ignition.msgs.Pose', '--reptype', 'ignition.msgs.Boolean',
                    '--timeout', '3000', '--req', req], capture_output=True)

def cube_z():
    r = subprocess.run(['ign', 'model', '-m', CUBE_NAME, '-p'], capture_output=True, text=True)
    m = re.search(r'\[\s*(-?[\d.eE+]+)\s+(-?[\d.eE+]+)\s+(-?[\d.eE+]+)\s*\]', r.stdout)
    return float(m.group(3)) if m else None

class Demo(Node):
    def __init__(self):
        super().__init__('demo_full')
        self.ap = self.create_publisher(JointTrajectory, '/crane_plus_arm_controller/joint_trajectory', 10)
        self.gp = self.create_publisher(JointTrajectory, '/crane_plus_gripper_controller/joint_trajectory', 10)
        self.arm = list(HOME); self.grip = OPEN
        self.js = None; self.n_msg = 0
        self.create_subscription(JointState, '/joint_states', self.cb, 10)
    def cb(self, m): self.js = m; self.n_msg += 1
    def hand(self):
        if not self.js: return None
        try: return self.js.position[self.js.name.index(GRIPPER_JOINT)]
        except Exception: return None
    def pub(self):
        jt = JointTrajectory(); jt.joint_names = ARM_JOINTS
        p = JointTrajectoryPoint(); p.positions = list(self.arm); p.time_from_start.nanosec = 100000000
        jt.points = [p]; self.ap.publish(jt)
        jg = JointTrajectory(); jg.joint_names = [GRIPPER_JOINT]
        q = JointTrajectoryPoint(); q.positions = [float(self.grip)]; q.time_from_start.nanosec = 100000000
        jg.points = [q]; self.gp.publish(jg)
    def goto(self, tgt, closed, dur):
        pa, pg = list(self.arm), self.grip
        tg = CLOSE if closed else OPEN
        n = max(1, int(dur * HZ))
        for i in range(1, n + 1):
            a = i / n
            self.arm = [x + (y - x) * a for x, y in zip(pa, tgt)]
            self.grip = pg + (tg - pg) * a
            self.pub(); rclpy.spin_once(self, timeout_sec=0.02); time.sleep(1.0 / HZ)
    def home(self, dur=1.5): self.goto(HOME, False, dur)

def grasp_and_present(d, lift, verbose=True):
    """把持→持ち上げ→差し出し を行い、(z_lift, z_present) を返す"""
    d.goto(ABOVE, False, 2.5)
    d.goto(DOWN, False, 2.5)
    d.goto(DOWN, True, 3.0)
    z_close = cube_z()
    d.goto(lift, True, 4.0)
    z_lift = cube_z()
    d.goto([0.0, lift[1], lift[2], lift[3]], True, 3.0)
    z_present = cube_z()
    if verbose:
        print('    close=%.4f  lift=%.4f  present=%.4f  hand=%.4f'
              % (z_close, z_lift, z_present, d.hand() if d.hand() is not None else float('nan')), flush=True)
    return z_lift, z_present

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--loops', type=int, default=1)
    ap.add_argument('--height', choices=sorted(HEIGHTS), default='low')
    ap.add_argument('--compare-heights', action='store_true')
    ap.add_argument('--no-reset', action='store_true')
    ap.add_argument('--reset-only', action='store_true')
    ap.add_argument('--home', action='store_true')
    a = ap.parse_args()

    if a.reset_only:
        set_cube(*CUBE); time.sleep(0.8)
        print('箱を (%.3f, %.3f, %.2f) に設置  z=%.4f' % (*CUBE, cube_z())); return

    rclpy.init(); d = Demo()
    t0 = time.time()
    while d.n_msg == 0 and time.time() - t0 < 8.0:
        rclpy.spin_once(d, timeout_sec=0.1)
    if d.n_msg == 0:
        print('!! /joint_states が届きません。Gazebo が ⏸ なら ▶ に。')
        d.destroy_node(); rclpy.shutdown(); return
    if a.home:
        print('homing...'); d.home(1.5); d.destroy_node(); rclpy.shutdown(); return

    # ---- 高さ4案を比較（最短・挨拶なし）----
    if a.compare_heights:
        print('高さ4案を比較します（把持→持ち上げ→差し出しのみ）', flush=True)
        for name in ('low', 'mid', 'high', 'higher'):
            if not a.no_reset:
                set_cube(*CUBE); time.sleep(0.8)
            print('  [%s] %s' % (name, HEIGHTS[name]), flush=True)
            zl, zp = grasp_and_present(d, HEIGHTS[name])
            print('    → %s   (箱 z: 掴んだ後 %.4f / 差し出し %.4f)\n'
                  % ('★ 保持OK' if (zp is not None and zp > Z_OK) else '× 落ちた', zl or 0.0, zp or 0.0), flush=True)
        d.destroy_node(); rclpy.shutdown(); return

    # ---- 通しシーケンス ----
    lift = HEIGHTS[a.height]
    for k in range(a.loops):
        print('--- 通し %d/%d  (高さ=%s)' % (k + 1, a.loops, a.height), flush=True)
        if not a.no_reset:
            set_cube(*CUBE); time.sleep(0.8)
            print('  箱を初期位置へ  z0=%.4f' % cube_z(), flush=True)
        for name, pose, closed, dur in GREETING:
            d.goto(pose, closed, dur)
        zl, zp = grasp_and_present(d, lift)
        d.goto([0.0, lift[1], lift[2], lift[3]], True, 0.8)   # 保持（短縮）
        zc = cube_z()
        print('  判定: %s (掴んだ後 %.4f / 差し出し後 %.4f)'
              % ('★ 成功（差し出しまで保持）' if (zc is not None and zc > Z_OK) else '× 途中で落ちた', zl or 0.0, zc or 0.0), flush=True)
    d.destroy_node(); rclpy.shutdown()

if __name__ == '__main__':
    main()
