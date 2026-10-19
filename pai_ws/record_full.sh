#!/usr/bin/env bash
# 通しシーケンス（お辞儀→手振り→把持→持ち上げ→差し出し）を N 本自動収録する
# ・毎回、箱を set_pose で初期位置に戻してから開始
# ・各エピソード後に「差し出しまで保持できたか」を判定してログに出し、成功/失敗を記録
#   使い方:  bash record_full.sh [N]        # 既定 N=20
set -e
N=${1:-20}
WS=/workspace/pai_ws
HEIGHT=${HEIGHT:-higher}    # 差し出しの高さ: low/mid/high/higher（例: HEIGHT=high bash record_full.sh 20）
OUT=/workspace/dataset/rosbags/pai_final_full
ARMT="/joint_states /crane_plus_arm_controller/joint_trajectory /crane_plus_gripper_controller/joint_trajectory"

# 学習に画像を使う場合に備えてカメラのトピックを自動検出して足す
CAM=$(ros2 topic list 2>/dev/null | grep -iE 'image_raw$' | head -1 || true)
TOPICS="$ARMT${CAM:+ $CAM}"

mkdir -p "$OUT"
LOG="$OUT/episodes.log"; : > "$LOG"
echo "topics: $TOPICS   height: $HEIGHT" | tee -a "$LOG"
OK=0; NG=0

for i in $(seq -w 1 "$N"); do
  echo "=== episode $i ===" | tee -a "$LOG"
  python3 "$WS/scripted_episode.py" --home >/dev/null 2>&1 || true   # 腕を直立に
  python3 "$WS/demo_full.py" --reset-only >>"$LOG" 2>&1              # 箱を初期位置へ

  ros2 bag record -o "$OUT/ep_$i" $TOPICS >/dev/null 2>&1 &
  REC=$!
  sleep 1.5

  OUTP=$(python3 "$WS/demo_full.py" --no-reset --height "$HEIGHT" 2>&1 || true)
  echo "$OUTP" >> "$LOG"
  if echo "$OUTP" | grep -q '★ 成功'; then
    echo "ep_$i: OK" | tee -a "$LOG"; OK=$((OK+1))
  else
    echo "ep_$i: NG（このテイクは学習に使わない）" | tee -a "$LOG"; NG=$((NG+1))
  fi

  sleep 0.5
  kill -INT "$REC" 2>/dev/null || true
  wait "$REC" 2>/dev/null || true
  sleep 1.5
done

echo "------------------------------------------" | tee -a "$LOG"
echo "完了: $OUT   成功 $OK / 失敗 $NG" | tee -a "$LOG"
echo "成功したテイクだけを使うには:  grep -E '^ep_[0-9]+: OK' $LOG" | tee -a "$LOG"
