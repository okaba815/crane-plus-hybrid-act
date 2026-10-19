# crane-plus-hybrid-act

Gazebo 上の **CRANE+ V2** に対して、模倣学習（**LeRobot ACT**）で
**「お辞儀 → 手振り → 把持 → 持ち上げ → 差し出し」** のハイブリッド動作を獲得させたプロジェクトです。

- 観測は**関節角度5次元のみ**（画像・カメラは使用しない）
- デモは**スクリプト生成**（20本収録 → 成功19本）して rosbag に記録
- **学習**: ACT / 5000 step / batch 4（CPU）→ **loss 0.11448**
- **推論**: 20Hz / `n_action_steps = 16` → **推論のみで全ステップ成功**

## デモ

| | |
|---|---|
| 動画 | YouTube（限定公開）https://youtu.be/TgjpHZ8moJ4 |
| 学習 loss | 0.11448（5000 step）|
| オフライン評価 | Mean L2 = 0.1383（episode 1, 520フレーム）|

---

## 動作の流れ

1. お辞儀（j2 = 0.8）
2. 手振り（j1: +0.5 → -0.5 → 0）
3. 箱の真上へ移動 → 下降して把持
4. 持ち上げ
5. 正面へ差し出し（higher 設定）

---

## 必要環境

- Ubuntu 22.04（Docker コンテナを想定）
- ROS 2 Humble + Gazebo（Ignition）
- CRANE+ V2 の記述パッケージ（`crane_plus_description` など）
- `pixi`（学習ワークスペース `pai_training`）

## セットアップ

```bash
# 1) ワークスペースのビルド
cd pai_ws && source /opt/ros/humble/setup.bash && colcon build

# 2) シミュレータ起動
source install/setup.bash
ros2 launch crane_plus_gazebo crane_plus_with_table.launch.py

# 3) 把持のための摩擦・質量パッチを適用（初回のみ）
bash patches/grasp_fix_patch.sh
```

> **重要**: グリッパ指の摩擦係数を `0.2 → 2.0` にしないと**箱を把持できません**
> （接触面の摩擦は「弱い側」に支配されるため、箱側だけを上げても効きません）。

## 使い方

### 1. デモ収録（20本）
```bash
bash pai_ws/record_full.sh 20
# 出力: /workspace/dataset/rosbags/pai_final_full/ep_01..20
# 成否: 同ディレクトリの episodes.log（NGテイクは学習から除外）
```

### 2. データ変換（rosbag → LeRobot）
```bash
cd pai_training
pixi run convert
```

### 3. 学習
```bash
cd pai_training
sed -i 's/^training_steps: .*/training_steps: 5000/' configs/train_config.yaml
sed -i 's/^batch_size: .*/batch_size: 4/' configs/train_config.yaml
WANDB_MODE=offline pixi run train
```

### 4. 推論
```bash
# 学習時と同じ初期状態にする
cd pai_ws && source install/setup.bash
python3 scripted_episode.py --home
python3 demo_full.py --reset-only

# 推論
cd pai_training
pixi run infer --model-path /home/ubuntu/checkpoints/train/crane_plus_hybrid_act
```
> `infer.py` の `self.policy = ACTPolicy.from_pretrained(...)` の直後に
> `self.policy.config.n_action_steps = 16` と `self.policy.n_action_steps = 16` を入れています。

### 5. 画面録画（任意）
```bash
ffmpeg -f x11grab -framerate 20 -i :0 -t 90 -y /workspace/videos/hybrid_run1.mp4
# 必要部分だけ切り出し
ffmpeg -ss 62 -i /workspace/videos/hybrid_run1.mp4 -t 35 -c:v libx264 -crf 18 -preset veryfast -y /workspace/videos/hybrid_run1_trim.mp4
```

---

## ディレクトリ構成

```
.
├── README.md
├── docs/
│   ├── report.md                 # レポート
│   └── videos/hybrid_run1_trim.mp4
├── pai_ws/                       # ROS / Gazebo ワークスペース
│   ├── demo_full.py              # 動作シーケンス生成（--height で高さ変更）
│   ├── record_full.sh            # 自動収録（リセット＋成否ログ）
│   └── scripted_episode.py       # 初期化・単発動作
├── pai_training/                 # 学習ワークスペース（pixi）
│   ├── scripts/
│   │   ├── infer.py              # リアルタイム推論
│   │   ├── rosbag2lerobot.py     # データ変換
│   │   ├── debug_policy.py       # オフライン評価
│   │   └── train.py
│   ├── configs/
│   │   ├── train_config.yaml
│   │   ├── conversion_config.yaml
│   │   └── crane_features.py
│   └── pyproject.toml
└── patches/
    └── grasp_fix_patch.sh        # 摩擦・質量の再現用
```

---

## つまずきと解決（再現時の注意）

| 症状 | 原因 | 対策 |
|---|---|---|
| 箱が滑り落ちる | **グリッパ指の摩擦が 0.2**（弱い側で決まる）| 指の `mu1/mu2` を **2.0**、箱も `mu=mu2=2.0`, `kp=1e6`, `mass=0.01` |
| 一歩目で止まる | 学習不足＋冒頭の静止が長い | 静止を短縮して再収録＋**5000 step** |
| 手振りで揺れ続ける／把持で止まる | **同じ姿勢に複数の意味**がある（履歴なし）| **`n_action_steps = 16`** |
| 動作を遅くしたい | ─ | タイマーごと低速化（20Hz→10Hz）。**関節指令の速度制限は逆効果** |

## 今後の課題
- 観測に履歴を導入（`delta_timestamps`）して曖昧性を根本解決
- 滑らかでゆっくりした動作（低速収録＋再学習）
- 成功率の定量評価、sim-to-real への展開

## 謝辞

本プロジェクトは「Physical AI 応用1講座」の最終課題として作成しました。
ロボットモデル（CRANE+ V2）、シミュレーション、および学習に使用した
ROS 2 / Gazebo / LeRobot の各オープンソースプロジェクトに感謝します。
