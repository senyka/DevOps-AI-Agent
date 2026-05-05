### `scripts/lora_manager.sh`
```bash
#!/bin/bash
# scripts/lora_manager.sh
# Управление LoRA адаптерами в vLLM

set -euo pipefail

VLLM_API="${VLLM_API:-http://localhost:8000/v1}"
ADAPTER_NAME="${1:-}"
ACTION="${2:-load}"  # load | unload | rollback | list

usage() {
  echo "Usage: $0 <adapter_name> <action>"
  echo "Actions: load, unload, rollback, list"
  exit 1
}

[[ -z "$ADAPTER_NAME" && "$ACTION" != "list" ]] && usage

case $ACTION in
  load)
    echo "📦 Loading adapter: $ADAPTER_NAME"
    curl -s -X POST "$VLLM_API/lora" \
      -H "Content-Type: application/json" \
      -d "{\"lora_name\": \"$ADAPTER_NAME\", \"lora_path\": \"/lora/$ADAPTER_NAME\"}" \
      | jq -r '. // empty'
    echo "✓ Loaded"
    ;;
    
  unload)
    echo "🗑️  Unloading adapter: $ADAPTER_NAME"
    curl -s -X DELETE "$VLLM_API/lora/$ADAPTER_NAME"
    echo "✓ Unloaded"
    ;;
    
  rollback)
    echo "🔄 Rolling back from: $ADAPTER_NAME"
    # Выгрузить текущий
    curl -s -X DELETE "$VLLM_API/lora/$ADAPTER_NAME" 2>/dev/null || true
    
    # Найти предыдущий
    PREV=$(ls -t /lora 2>/dev/null | grep "devops_v" | sed -n "2p" || true)
    if [[ -n "$PREV" && -d "/lora/$PREV" ]]; then
      echo "📥 Loading previous: $PREV"
      curl -s -X POST "$VLLM_API/lora" \
        -H "Content-Type: application/json" \
        -d "{\"lora_name\": \"$PREV\", \"lora_path\": \"/lora/$PREV\"}"
      echo "✓ Rolled back to $PREV"
    else
      echo "⚠ No previous adapter — running base model"
    fi
    ;;
    
  list)
    echo "📋 Available adapters:"
    curl -s "$VLLM_API/lora" | jq -r '.[].lora_name' 2>/dev/null || echo "(none)"
    echo ""
    echo "📁 Local adapters:"
    ls -1 /lora 2>/dev/null | grep "devops_v" || echo "(none)"
    ;;
    
  *)
    usage
    ;;
esac
```

---
