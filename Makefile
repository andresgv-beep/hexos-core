# ============================================================================
# HELIOS COGNITIVE ECOSYSTEM
# Master Makefile
# ============================================================================
#
#   "El cuerpo que protege la mente"
#
#   ┌─────────────────────────────────────────────────────────────────────┐
#   │                          ARQUITECTURA                               │
#   ├─────────────────────────────────────────────────────────────────────┤
#   │                                                                     │
#   │   ┌─────────────┐                                                   │
#   │   │  HNF-EXT    │  Identidad + Strong Memories (El Alma)           │
#   │   └──────┬──────┘                                                   │
#   │          │                                                          │
#   │   ┌──────┴──────┐                                                   │
#   │   │    HERA     │  Coordinador de memoria (El Cerebro)             │
#   │   └──────┬──────┘                                                   │
#   │          │                                                          │
#   │   ┌──────┴──────┐                                                   │
#   │   │ MEMORY_CORE │  Almacenamiento episódico/semántico              │
#   │   └──────┬──────┘                                                   │
#   │          │                                                          │
#   │   ┌──────┴──────┐                                                   │
#   │   │  HEXOS_BUS  │  IPC compartido (/dev/shm/hexos_state)           │
#   │   └──────┬──────┘                                                   │
#   │          │                                                          │
#   │   ┌──────┴──────┐                                                   │
#   │   │   HEXOS     │  Supervisor de hardware (El Cuerpo)              │
#   │   └─────────────┘                                                   │
#   │                                                                     │
#   └─────────────────────────────────────────────────────────────────────┘
#
# ============================================================================

.PHONY: all clean hexos memory_core hnf_ext hera test info

# Build all modules
all: hexos memory_core hnf_ext hera cognitive_stub
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║  HELIOS ECOSYSTEM BUILD COMPLETE                             ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo ""

# Individual modules
hexos:
	@echo "Building HEXOS..."
	@$(MAKE) -C hexos

memory_core:
	@echo "Building Memory Core..."
	@$(MAKE) -C memory_core

hnf_ext:
	@echo "Building HNF-EXT..."
	@$(MAKE) -C hnf_ext

hera:
	@echo "Building HERA..."
	@$(MAKE) -C hera

cognitive_stub:
	@echo "Building Cognitive Kernel (stub)..."
	@$(MAKE) -C cognitive_stub

# Run all tests
test: all
	@echo ""
	@echo "Running HEXOS test..."
	@cd hexos && ./bin/hexos --help || true
	@echo ""
	@echo "Running Memory Core test..."
	@cd memory_core && ./bin/mc_test
	@echo ""
	@echo "Running HNF-EXT test..."
	@cd hnf_ext && ./bin/hnf_ext_test

# Clean all
clean:
	@$(MAKE) -C hexos clean 2>/dev/null || true
	@$(MAKE) -C memory_core clean 2>/dev/null || true
	@$(MAKE) -C hnf_ext clean 2>/dev/null || true
	@$(MAKE) -C hera clean 2>/dev/null || true
	@$(MAKE) -C cognitive_stub clean 2>/dev/null || true
	@echo "All modules cleaned"

# Info
info:
	@echo ""
	@echo "HELIOS COGNITIVE ECOSYSTEM"
	@echo "=========================="
	@echo ""
	@echo "Modules:"
	@echo "  hexos/        - Hardware supervisor (C)"
	@echo "  memory_core/  - Memory storage system (C)"
	@echo "  hnf_ext/      - Identity/soul block (C)"
	@echo "  hera/         - Memory coordinator (C) [pending]"
	@echo "  cognitive_stub/ - Inference simulator [pending]"
	@echo ""
	@echo "Commands:"
	@echo "  make          - Build all modules"
	@echo "  make test     - Build and run tests"
	@echo "  make clean    - Clean all builds"
	@echo "  make hexos    - Build only HEXOS"
	@echo "  make memory_core - Build only Memory Core"
	@echo "  make hnf_ext  - Build only HNF-EXT"
	@echo ""
