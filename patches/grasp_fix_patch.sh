#!/usr/bin/env bash
# grasp_fix_patch.sh — 把持が成立するシミュレーション設定を1コマンドで再現する
#   （cube_friction_patch.sh の後継。木箱とグリッパ（指）の両方を修正します）
#   使い方:  bash grasp_fix_patch.sh    → そのあと Gazebo(launch) を再起動
set -e

echo "=== 1) 木箱 wood_cube_5cm の修正 ==="
D="/home/ubuntu/.ignition/fuel/fuel.ignitionrobotics.org/openrobotics/models/wood%20cube%205cm/3"
cd "$D"
[ -f model.sdf.bak ] || cp model.sdf model.sdf.bak     # 元の状態を一度だけ保存

python3 - <<'PY'
p = 'model.sdf'
s = open(p).read()
# 滑り摩擦 mu/mu2（未指定だと滑る）
if '<mu>' not in s:
    s = s.replace('<friction>',
        '<friction>\n'
        '                        <ode>\n'
        '                            <mu>2.0</mu>\n'
        '                            <mu2>2.0</mu2>\n'
        '                        </ode>', 1)
# 接触を硬く
s = s.replace('<kp>100000</kp>', '<kp>1000000</kp>')
# 質量 10g（軽いほど保持しやすい＝安定化措置）
for a in ('<mass>0.0565</mass>', '<mass>0.05</mass>', '<mass>0.02</mass>'):
    s = s.replace(a, '<mass>0.01</mass>')
for v in ('2.3541666666666672e-05', '8.333333333333333e-06', '2.0833333333333333e-05'):
    s = s.replace(v, '4.1666666666666667e-06')
open(p, 'w').write(s)
print('cube: mu=2.0 / kp=1e6 / mass=0.01')
PY
grep -n "mass>\|mu>\|mu2>\|kp>" model.sdf

echo
echo "=== 2) グリッパ（指）の摩擦修正 ==="
F=/home/ubuntu/airobot_ws/install/crane_plus_description/share/crane_plus_description/urdf/crane_plus.gazebo.xacro
[ -f "$F.bak" ] || cp "$F" "$F.bak"

python3 - "$F" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
key = '<gazebo reference="${name_link_hand}">'
i = s.index(key)
j = s.index('</gazebo>', i)
blk = s[i:j]
# ハンドのブロック内の mu1/mu2 を全部消して、2.0 の一組だけにする（重複防止）
blk = re.sub(r'(\s*<mu1>[^<]*</mu1>\s*<mu2>[^<]*</mu2>)+', '', blk)
blk = blk.rstrip() + '\n      <mu1>2.0</mu1>\n      <mu2>2.0</mu2>\n    '
s = s[:i] + blk + s[j:]
open(p, 'w').write(s)
print('gripper: hand mu1/mu2 -> 2.0（0.2 から10倍）')
PY
grep -n -A8 "name_link_hand" "$F" | head -14

echo
echo "完了。Gazebo(launch) を再起動して反映してください。"
