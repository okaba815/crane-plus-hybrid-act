#!/usr/bin/env bash
# =============================================================================
# rate_test.sh  v4 — 成功率の測定（初期化 → 推論 を N 回）
#
#   使い方:  cd /workspace && bash rate_test.sh 5
#   集計  :  python3 analyze_rate.py /workspace/rate_test
#
# v4 で直したこと（v1〜v3 の不具合）
#   [v1] 初期化にタイムアウトが無く、Gazebo が無いと無限に待って止まらなかった
#        → すべてのステップに個別タイムアウトを設定
#   [v2] 事前チェックに `ros2 topic echo --once` を使ったが、この ROS の
#        バージョンでは非対応で必ず失敗した
#        → `ros2 topic hz /clock | grep "average rate"` に変更
#   [v3] 初期化の出力を捨てていたため、失敗の理由が分からなかった
#        → 出力を reset_XX.log に全部保存し、失敗時は末尾を画面に表示
#   [v4] さらに: 開始時に古いプロセスを自動掃除／失敗しても止まらず継続／
#        各試行のサマリを最後に表示
#   [v5] `set -u` をやめた。ROS / pixi の setup スクリプトは未定義変数を参照
#        することがあり、`set -u` だと「初期化が失敗した」ように見えてしまう
#        （手動では2.4秒で成功していたのに、スクリプト経由だけ失敗した原因）
# =============================================================================

# 注意: `set -u` は使わない（ROS/pixi の setup スクリプトと相性が悪い）
set +u

N="${1:-5}"
MODEL="/home/ubuntu/checkpoints/train/crane_plus_hybrid_act"
OUT="/workspace/rate_test"
mkdir -p "$OUT"

log() { echo "[$(date +%H:%M:%S)] $*"; }
rule() { echo "------------------------------------------------------------"; }

# ---------------------------------------------------------------- STEP 0
log "STEP0: 古いプロセスを掃除します"
pkill -f "pixi run infer"  2>/dev/null || true
pkill -f "scripts/infer.py" 2>/dev/null || true
pkill -f scripted_episode  2>/dev/null || true
pkill -f demo_full.py      2>/dev/null || true
sleep 2
log "STEP0: 完了"

# ---------------------------------------------------------------- STEP 1
log "STEP1: Gazebo の動作確認（/clock）"
CLOCK_OK=0
for t in 1 2 3; do
  if timeout 10 bash -c 'source /opt/ros/humble/setup.bash >/dev/null 2>&1 || true; ros2 topic hz /clock 2>&1' \
       | grep -q "average rate"; then
    CLOCK_OK=1; break
  fi
  sleep 2
done
if [ "$CLOCK_OK" != "1" ]; then
  echo
  echo "❌ Gazebo が動いていません（/clock にメッセージが流れていません）"
  echo
  echo "  VNCデスクトップ側のターミナルで先に起動してください:"
  echo "    cd /workspace/pai_ws"
  echo "    source install/setup.bash"
  echo "    ros2 launch crane_plus_gazebo crane_plus_with_table.launch.py"
  echo
  echo "  → ウィンドウが出たら【左下が ▶（再生）】か確認"
  echo
  exit 1
fi
log "STEP1: ✅ Gazebo 動作中"
rule

# ---------------------------------------------------------------- STEP 2
log "成功率テスト開始: ${N} 回"
rule

SUMMARY=""
for i in $(seq 1 "$N"); do
  IDX=$(printf "%02d" "$i")
  log "===== 試行 ${i}/${N} ====="

  # --- 2a) 初期化（出力はすべて reset_XX.log に保存） ---
  (
    cd /workspace/pai_ws                     || exit 10
    source install/setup.bash                || exit 11
    echo "--- scripted_episode.py --home ---"
    timeout 60 python3 scripted_episode.py --home   || exit 12
    echo "--- demo_full.py --reset-only ---"
    timeout 60 python3 demo_full.py --reset-only    || exit 13
  ) > "$OUT/reset_${IDX}.log" 2>&1
  RC=$?

  if [ "$RC" -ne 0 ]; then
    log "⚠ 初期化に失敗しました（exit=${RC}）→ reset_${IDX}.log の末尾:"
    tail -12 "$OUT/reset_${IDX}.log" | sed 's/^/    /'
    log "  ※ この試行もそのまま続行します。結果は目視で必ず確認してください"
  else
    log "初期化 OK"
  fi
  sleep 2

  # --- 2b) 推論（75秒で自動終了） ---
  log "▶ 推論を開始します（75秒）。動きを観察してください"
  (
    cd /workspace/pai_training               || exit 20
    WANDB_MODE=offline timeout --foreground -k 5 75 \
      pixi run infer --model-path "$MODEL"
  ) > "$OUT/trial_${IDX}.log" 2>&1

  FR=$(grep -c "action:" "$OUT/trial_${IDX}.log" 2>/dev/null || true)
  FR=${FR:-0}
  if [ "$FR" -eq 0 ]; then
    log "■ 試行 ${i} 終了（記録フレーム: 0）⚠ 状態が取れていません"
    log "    → Gazebo の ▶ と初期化ログ（reset_${IDX}.log）を確認してください"
    SUMMARY="${SUMMARY}  試行${i}: フレーム0（要確認）\n"
  else
    log "■ 試行 ${i} 終了（記録フレーム: ${FR}）"
    SUMMARY="${SUMMARY}  試行${i}: フレーム ${FR}\n"
  fi
  rule
done

# ---------------------------------------------------------------- STEP 3
log "全 ${N} 回 完了"
echo
echo "=== サマリ ==="
printf "%b" "$SUMMARY"
echo
echo "自動判定:  python3 analyze_rate.py ${OUT}"
echo "ログ:      ${OUT}/trial_XX.log（推論）, reset_XX.log（初期化）"
echo "※ 最終的な正解は目視の結果（完走できたか）です。"
