#!/usr/bin/env python3
"""rate_test.sh が出力した trial_XX.log を解析して、成功率の目安を出す。

判定の考え方:
  - 「グリッパを閉じた」  : gripper の出力が 0.5 を超えた
  - 「持ち上げ姿勢に到達」: j2 が -0.400、j3 が -1.200（higher の持ち上げ姿勢）に近づいた
  → 両方そろえば「把持して持ち上げた」と推定できる
※ 箱が実際に保持できていたかは目視が最終判断です。

使い方:  python3 analyze_rate.py /workspace/rate_test
"""
import glob
import os
import re
import sys

# higher の持ち上げ姿勢（infer.py の関節順: j1, j2, j4, j3）
LIFT = (-1.571, -0.400, -1.550, -1.200)
TOL = 0.15

NUM = re.compile(r"-?\d+\.?\d*")


def analyze(path):
    frames = 0
    grasp = False   # グリッパを閉じた
    lift = False    # 持ち上げ姿勢に到達
    for line in open(path, errors="ignore"):
        if "action:" not in line or "gripper:" not in line:
            continue
        try:
            a_txt = line.split("action:")[1].split("gripper:")[0]
            g_txt = line.split("gripper:")[1]
            a = [float(x) for x in NUM.findall(a_txt)]
            g = float(NUM.findall(g_txt)[0])
        except Exception:
            continue
        frames += 1
        if g > 0.5:
            grasp = True
        if len(a) >= 4 and abs(a[1] - LIFT[1]) < TOL and abs(a[3] - LIFT[3]) < TOL:
            lift = True
    return frames, grasp, lift


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "/workspace/rate_test"
    logs = sorted(glob.glob(os.path.join(root, "trial_*.log")))
    if not logs:
        print("trial_*.log が見つかりません:", root)
        return

    rows = []
    for p in logs:
        frames, grasp, lift = analyze(p)
        ok = grasp and lift
        rows.append(ok)
        print(
            f"{os.path.basename(p)}: フレーム={frames:4d}  "
            f"グリッパ閉={str(grasp):5s}  持ち上げ到達={str(lift):5s}  "
            f"→ {'OK' if ok else 'NG'}"
        )

    n_ok = sum(1 for r in rows if r)
    print(f"\n自動判定: {n_ok} / {len(rows)} 成功（{100.0 * n_ok / len(rows):.0f}%）")
    print("※ 目視の結果が最終的な正解です（自動判定は補助）。")


if __name__ == "__main__":
    main()
