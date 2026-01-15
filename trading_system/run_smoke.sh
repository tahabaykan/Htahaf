#!/bin/bash
# run_smoke.sh - End-to-end smoke test script
# Bu script tüm servisleri sırayla başlatır ve smoke test yapar

set -e  # Hata durumunda dur

# Renkler
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Log fonksiyonu
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Cleanup fonksiyonu
cleanup() {
    log_info "Cleaning up processes..."
    pkill -f "python.*publish_tick.py" || true
    pkill -f "python.*engine/core.py" || true
    pkill -f "python.*router/order_router.py" || true
    pkill -f "python.*db/writer.py" || true
    pkill -f "python.*ui/pyqt_client.py" || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Virtualenv kontrolü
if [ ! -d ".venv" ]; then
    log_warn "Virtualenv bulunamadı, oluşturuluyor..."
    python3 -m venv .venv
fi

# Virtualenv aktif et
log_info "Virtualenv aktif ediliyor..."
source .venv/bin/activate

# Requirements kontrolü
if ! python -c "import aioredis" 2>/dev/null; then
    log_info "Requirements yükleniyor..."
    pip install -r requirements.txt -q
fi

# Docker kontrolü
log_info "Docker servisleri kontrol ediliyor..."
if ! docker compose ps | grep -q "redis.*Up"; then
    log_info "Redis başlatılıyor..."
    docker compose up -d redis postgres
    sleep 3
fi

# Redis bağlantı testi
log_info "Redis bağlantı testi..."
if ! redis-cli ping > /dev/null 2>&1; then
    log_error "Redis'e bağlanılamıyor! Docker compose up -d redis çalıştırın."
    exit 1
fi
log_info "Redis bağlantısı başarılı ✓"

# Stream'leri temizle (opsiyonel)
read -p "Redis stream'lerini temizlemek ister misiniz? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "Redis stream'leri temizleniyor..."
    redis-cli DEL ticks signals orders execs > /dev/null 2>&1 || true
    redis-cli DEL "ticks:strategy_group" "signals:risk_group" "orders:router_group" > /dev/null 2>&1 || true
fi

# Test süresi (saniye)
TEST_DURATION=${TEST_DURATION:-30}
log_info "Smoke test başlatılıyor (süre: ${TEST_DURATION}s)..."

# Log dizini
mkdir -p logs
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 1. Tick Publisher
log_info "1/5 Tick Publisher başlatılıyor..."
python collector/publish_tick.py > logs/publisher_${TIMESTAMP}.log 2>&1 &
PUBLISHER_PID=$!
sleep 2
if ! kill -0 $PUBLISHER_PID 2>/dev/null; then
    log_error "Publisher başlatılamadı!"
    exit 1
fi
log_info "Publisher PID: $PUBLISHER_PID ✓"

# 2. Engine
log_info "2/5 Engine başlatılıyor..."
python engine/core.py > logs/engine_${TIMESTAMP}.log 2>&1 &
ENGINE_PID=$!
sleep 3
if ! kill -0 $ENGINE_PID 2>/dev/null; then
    log_error "Engine başlatılamadı!"
    kill $PUBLISHER_PID 2>/dev/null || true
    exit 1
fi
log_info "Engine PID: $ENGINE_PID ✓"

# 3. Risk Manager (opsiyonel)
read -p "Risk Manager başlatılsın mı? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "3/6 Risk Manager başlatılıyor..."
    python engine/risk.py > logs/risk_${TIMESTAMP}.log 2>&1 &
    RISK_PID=$!
    sleep 2
    log_info "Risk Manager PID: $RISK_PID ✓"
else
    RISK_PID=""
    log_info "3/5 Risk Manager atlandı"
fi

# 4. Router (Mock mode)
log_info "$([ -n "$RISK_PID" ] && echo "4/6" || echo "3/5") Router başlatılıyor (MOCK mode)..."
python router/order_router.py > logs/router_${TIMESTAMP}.log 2>&1 &
ROUTER_PID=$!
sleep 3
if ! kill -0 $ROUTER_PID 2>/dev/null; then
    log_error "Router başlatılamadı!"
    kill $PUBLISHER_PID $ENGINE_PID $RISK_PID 2>/dev/null || true
    exit 1
fi
log_info "Router PID: $ROUTER_PID ✓"

# 5. DB Writer (opsiyonel - Postgres yoksa atla)
if docker compose ps | grep -q "postgres.*Up"; then
    log_info "$([ -n "$RISK_PID" ] && echo "5/6" || echo "4/5") DB Writer başlatılıyor..."
    python db/writer.py > logs/writer_${TIMESTAMP}.log 2>&1 &
    WRITER_PID=$!
    sleep 2
    log_info "DB Writer PID: $WRITER_PID ✓"
else
    WRITER_PID=""
    log_warn "Postgres çalışmıyor, DB Writer atlandı"
fi

# 6. UI (opsiyonel)
read -p "PyQt UI başlatılsın mı? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "$([ -n "$WRITER_PID" ] && echo "6/6" || echo "5/5") PyQt UI başlatılıyor..."
    python ui/pyqt_client.py > logs/ui_${TIMESTAMP}.log 2>&1 &
    UI_PID=$!
    log_info "UI PID: $UI_PID ✓"
    log_warn "UI manuel olarak kapatılmalı"
else
    UI_PID=""
fi

# Test süresi bekle
log_info "Test çalışıyor... (${TEST_DURATION} saniye)"
sleep $TEST_DURATION

# Metrikleri topla
log_info "=== Smoke Test Sonuçları ==="

# Redis stream uzunlukları
TICKS_COUNT=$(redis-cli XLEN ticks 2>/dev/null || echo "0")
SIGNALS_COUNT=$(redis-cli XLEN signals 2>/dev/null || echo "0")
ORDERS_COUNT=$(redis-cli XLEN orders 2>/dev/null || echo "0")
EXECS_COUNT=$(redis-cli XLEN execs 2>/dev/null || echo "0")

log_info "Ticks stream: $TICKS_COUNT mesaj"
log_info "Signals stream: $SIGNALS_COUNT mesaj"
log_info "Orders stream: $ORDERS_COUNT mesaj"
log_info "Execs stream: $EXECS_COUNT mesaj"

# Başarı kriterleri
SUCCESS=true

if [ "$TICKS_COUNT" -eq 0 ]; then
    log_error "Ticks stream boş - Publisher çalışmıyor olabilir"
    SUCCESS=false
fi

if [ "$SIGNALS_COUNT" -eq 0 ] && [ "$TICKS_COUNT" -gt 0 ]; then
    log_error "Signals stream boş - Engine çalışmıyor olabilir"
    SUCCESS=false
fi

if [ "$EXECS_COUNT" -eq 0 ] && [ "$ORDERS_COUNT" -gt 0 ]; then
    log_warn "Execs stream boş - Router execution yazmıyor olabilir (normal mock mode'da)"
fi

# Process durumları
log_info "=== Process Durumları ==="
for pid_name in "PUBLISHER_PID:Publisher" "ENGINE_PID:Engine" "ROUTER_PID:Router" "WRITER_PID:Writer"; do
    IFS=':' read -r var_name display_name <<< "$pid_name"
    pid=${!var_name}
    if [ -n "$pid" ] && kill -0 $pid 2>/dev/null; then
        log_info "$display_name: Çalışıyor (PID: $pid) ✓"
    elif [ -n "$pid" ]; then
        log_error "$display_name: Çalışmıyor (PID: $pid) ✗"
        SUCCESS=false
    fi
done

# Sonuç
echo
if [ "$SUCCESS" = true ]; then
    log_info "=== SMOKE TEST BAŞARILI ✓ ==="
    log_info "Log dosyaları: logs/"
    log_info "Devam etmek için Ctrl+C ile durdurun"
    
    # Sürekli çalıştır (Ctrl+C ile durdur)
    while true; do
        sleep 1
    done
else
    log_error "=== SMOKE TEST BAŞARISIZ ✗ ==="
    log_info "Log dosyalarını kontrol edin: logs/"
    cleanup
    exit 1
fi








