#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Fagan Inspection Tool - Run Script
# =============================================================================
# Usage:
#   ./run_example.sh dry-run    # Test ohne API-Key
#   ./run_example.sh ubr        # UBR-Inspektion + Evaluation
#   ./run_example.sh cbr        # CBR-Inspektion + Evaluation
#   ./run_example.sh full       # UBR + CBR + Gold-Checksums
# =============================================================================

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Hilfsfunktionen
# -----------------------------------------------------------------------------

print_header() {
    echo ""
    echo -e "${BLUE}=== $1 ===${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

show_usage() {
    echo "Fagan Inspection Tool - Run Script"
    echo ""
    echo "Usage: $0 <mode>"
    echo ""
    echo "Modi:"
    echo "  dry-run    Test ohne API-Key (simulierte Ergebnisse)"
    echo "  ubr        UBR-Inspektion (Usage-Based Reading) + Evaluation"
    echo "  cbr        CBR-Inspektion (Checklist-Based Reading) + Evaluation"
    echo "  full       Kompletter Run: UBR + CBR + Gold-Checksums"
    echo ""
    echo "Beispiele:"
    echo "  $0 dry-run   # Schnelltest ohne API-Key"
    echo "  $0 ubr       # UBR-Run mit Evaluation"
    echo "  $0 full      # Kompletter Durchlauf"
    echo ""
    echo "Voraussetzungen:"
    echo "  - Python venv aktiviert: source .venv/bin/activate"
    echo "  - Tool installiert: pip install -e ."
    echo "  - .env mit OPENAI_API_KEY (außer dry-run)"
    exit 1
}

check_prerequisites() {
    print_header "Prüfe Voraussetzungen"

    # Prüfe ob fagan CLI verfügbar ist
    if ! command -v fagan &> /dev/null; then
        print_error "fagan CLI nicht gefunden!"
        echo "  Bitte installieren: pip install -e ."
        exit 1
    fi
    print_success "fagan CLI verfügbar"

    # Prüfe wichtige Dateien
    local required_files=(
        "configs/examples/c1_ubr.yaml"
        "configs/examples/c1_cbr.yaml"
        "artifacts/gold/Faults_List_In_ver6.xls"
    )

    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            print_error "Datei nicht gefunden: $file"
            exit 1
        fi
    done
    print_success "Alle erforderlichen Dateien vorhanden"
}

load_env() {
    if [[ -f ".env" ]]; then
        set -a
        source .env
        set +a
        print_success ".env geladen"
    else
        print_warning ".env nicht gefunden"
    fi
}

check_api_key() {
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
        print_error "OPENAI_API_KEY nicht gesetzt!"
        echo "  Erstelle .env: cp .env.example .env"
        echo "  Dann OPENAI_API_KEY eintragen"
        exit 1
    fi
    print_success "OPENAI_API_KEY gesetzt (${OPENAI_API_KEY:0:8}...)"
}

show_gold_checksums() {
    print_header "Gold-Standard Checksums"
    shasum -a 256 artifacts/gold/Faults_List_In_ver6.xls artifacts/gold/README.md
}

show_results() {
    local run_id="$1"
    echo ""
    echo "Ergebnisse:"
    echo "  Defekte: runs/$run_id/final_defects.json"
    echo "  Metriken: eval/$run_id/metrics.json"
    if [[ -d "runs/$run_id" ]]; then
        echo ""
        echo "runs/$run_id/:"
        ls -la "runs/$run_id/" 2>/dev/null || true
    fi
    if [[ -d "eval/$run_id" ]]; then
        echo ""
        echo "eval/$run_id/:"
        ls -la "eval/$run_id/" 2>/dev/null || true
    fi
}

# -----------------------------------------------------------------------------
# Modi
# -----------------------------------------------------------------------------

run_dry_run() {
    print_header "Dry-Run (ohne API-Key)"

    check_prerequisites

    echo "Starte fagan dry-run..."
    fagan dry-run

    print_success "Dry-Run abgeschlossen"
    echo ""
    echo "Ergebnisse: runs/demo_dry_run/"
    ls -la runs/demo_dry_run/ 2>/dev/null || true
}

run_ubr() {
    print_header "UBR-Inspektion (Usage-Based Reading)"

    check_prerequisites
    load_env
    check_api_key

    local RUN_ID="thesis_ubr_check_$(date +%Y%m%d_%H%M%S)"
    echo "RUN_ID: $RUN_ID"
    echo ""

    echo "Starte UBR-Inspektion..."
    fagan run --config configs/examples/c1_ubr.yaml --run-id "$RUN_ID"

    # Prüfe ob Run erfolgreich war
    if [[ ! -f "runs/$RUN_ID/final_defects.json" ]]; then
        print_error "Run fehlgeschlagen - keine Ergebnisse"
        exit 1
    fi
    print_success "UBR-Inspektion abgeschlossen"

    echo ""
    echo "Starte Evaluation..."
    fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65

    print_success "Evaluation abgeschlossen"
    show_results "$RUN_ID"
}

run_cbr() {
    print_header "CBR-Inspektion (Checklist-Based Reading)"

    check_prerequisites
    load_env
    check_api_key

    local RUN_ID="thesis_cbr_check_$(date +%Y%m%d_%H%M%S)"
    echo "RUN_ID: $RUN_ID"
    echo ""

    echo "Starte CBR-Inspektion..."
    fagan run --config configs/examples/c1_cbr.yaml --run-id "$RUN_ID"

    # Prüfe ob Run erfolgreich war
    if [[ ! -f "runs/$RUN_ID/final_defects.json" ]]; then
        print_error "Run fehlgeschlagen - keine Ergebnisse"
        exit 1
    fi
    print_success "CBR-Inspektion abgeschlossen"

    echo ""
    echo "Starte Evaluation..."
    fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65

    print_success "Evaluation abgeschlossen"
    show_results "$RUN_ID"
}

run_full() {
    print_header "Kompletter Run: UBR + CBR + Gold-Checksums"

    check_prerequisites
    load_env
    check_api_key

    # Gold-Checksums vorher
    echo "Gold-Checksums VORHER:"
    show_gold_checksums
    local CHECKSUM_BEFORE
    CHECKSUM_BEFORE=$(shasum -a 256 artifacts/gold/Faults_List_In_ver6.xls | cut -d' ' -f1)

    # UBR Run
    print_header "1/4: UBR-Inspektion"
    local RUN_ID_UBR="thesis_ubr_full_$(date +%Y%m%d_%H%M%S)"
    echo "RUN_ID_UBR: $RUN_ID_UBR"
    fagan run --config configs/examples/c1_ubr.yaml --run-id "$RUN_ID_UBR"

    if [[ ! -f "runs/$RUN_ID_UBR/final_defects.json" ]]; then
        print_error "UBR-Run fehlgeschlagen"
        exit 1
    fi
    print_success "UBR-Inspektion abgeschlossen"

    # UBR Eval
    print_header "2/4: UBR-Evaluation"
    fagan eval --run "$RUN_ID_UBR" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65
    print_success "UBR-Evaluation abgeschlossen"

    # CBR Run
    print_header "3/4: CBR-Inspektion"
    local RUN_ID_CBR="thesis_cbr_full_$(date +%Y%m%d_%H%M%S)"
    echo "RUN_ID_CBR: $RUN_ID_CBR"
    fagan run --config configs/examples/c1_cbr.yaml --run-id "$RUN_ID_CBR"

    if [[ ! -f "runs/$RUN_ID_CBR/final_defects.json" ]]; then
        print_error "CBR-Run fehlgeschlagen"
        exit 1
    fi
    print_success "CBR-Inspektion abgeschlossen"

    # CBR Eval
    print_header "4/4: CBR-Evaluation"
    fagan eval --run "$RUN_ID_CBR" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65
    print_success "CBR-Evaluation abgeschlossen"

    # Gold-Checksums nachher
    print_header "Gold-Checksums NACHHER"
    show_gold_checksums
    local CHECKSUM_AFTER
    CHECKSUM_AFTER=$(shasum -a 256 artifacts/gold/Faults_List_In_ver6.xls | cut -d' ' -f1)

    # Checksum-Vergleich
    if [[ "$CHECKSUM_BEFORE" == "$CHECKSUM_AFTER" ]]; then
        print_success "Gold-Standard UNVERÄNDERT"
    else
        print_error "Gold-Standard wurde verändert!"
        exit 1
    fi

    # Zusammenfassung
    print_header "Zusammenfassung"
    echo "UBR Run: $RUN_ID_UBR"
    echo "CBR Run: $RUN_ID_CBR"
    echo ""
    echo "Ergebnisse:"
    echo "  UBR Defekte: runs/$RUN_ID_UBR/final_defects.json"
    echo "  UBR Metriken: eval/$RUN_ID_UBR/metrics.json"
    echo "  CBR Defekte: runs/$RUN_ID_CBR/final_defects.json"
    echo "  CBR Metriken: eval/$RUN_ID_CBR/metrics.json"
    echo ""
    print_success "Kompletter Run abgeschlossen"
}

# -----------------------------------------------------------------------------
# Hauptprogramm
# -----------------------------------------------------------------------------

MODE="${1:-}"

case "$MODE" in
    dry-run)
        run_dry_run
        ;;
    ubr)
        run_ubr
        ;;
    cbr)
        run_cbr
        ;;
    full)
        run_full
        ;;
    *)
        show_usage
        ;;
esac
