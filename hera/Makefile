# ============================================================================
# HERA v3.0 Makefile
# HELIOS Cognitive Ecosystem
#
# "HERA ES LA MENTE. HEXOS ES EL CUERPO."
# ============================================================================

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2 -g -D_GNU_SOURCE
LDFLAGS = -lpthread -lrt -lm

# Optional: Link with Memory Core and HNF-EXT
# Uncomment these if building integrated
# CFLAGS += -DMEMORY_CORE_AVAILABLE -DHNF_EXT_AVAILABLE
# LDFLAGS += -L../memory_core/bin -lmemory_core -L../hnf_ext/bin -lhnf_ext

# Directories
SRCDIR = src
INCDIR = include
OBJDIR = obj
BINDIR = bin

# Source files
CORE_SRC = $(SRCDIR)/hera.c
STORE_SRC = $(SRCDIR)/hera_store.c
MENTE_SRC = $(SRCDIR)/hera_profile.c $(SRCDIR)/hera_delta.c

ALL_SRC = $(CORE_SRC) $(STORE_SRC) $(MENTE_SRC)

# Object files
OBJECTS = $(patsubst $(SRCDIR)/%.c,$(OBJDIR)/%.o,$(ALL_SRC))

# Library target
LIB_TARGET = $(BINDIR)/libhera.a

# Test target
TEST_TARGET = $(BINDIR)/hera_test

# ============================================================================
# Rules
# ============================================================================

.PHONY: all clean lib test store-test mente-test cli sabotaje sabotaje-mente sabotaje-carrera carrera auditar

all: lib test store-test mente-test cli auditar

lib: $(LIB_TARGET)

$(LIB_TARGET): $(OBJECTS)
	@mkdir -p $(BINDIR)
	ar rcs $@ $(OBJECTS)
	@echo ""
	@echo "Library built: $@"

$(OBJDIR)/%.o: $(SRCDIR)/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -I$(INCDIR) -c $< -o $@

test: $(TEST_TARGET)

$(TEST_TARGET): tools/hera_test.c $(LIB_TARGET)
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -I$(INCDIR) $< -L$(BINDIR) -lhera $(LDFLAGS) -o $@
	@echo ""
	@echo "Test program built: $@"

clean:
	rm -rf $(OBJDIR) $(BINDIR)

# ============================================================================
# E3 — barrera del almacén de memoria
# ============================================================================
# `make sabotaje` compila el almacén roto de tres formas distintas y exige que
# la batería lo detecte. Una batería que solo se ha visto pasar no demuestra
# nada: hay que verla fallar cuando el código está mal.

STORE_TEST = $(BINDIR)/hera_store_test
# Un sabotaje que no compila, que muere o que no se detecta hace fallar la
# puerta. Antes se tragaba un segfault en silencio y seguia diciendo OK.
SABOTAJES  = 1 2 3 4 5 6 7 8 9
MENTE_TEST = $(BINDIR)/hera_mente_test
MENTE_SABOTAJES = 20 21 22

store-test: $(STORE_TEST)

$(STORE_TEST): tools/hera_store_test.c $(STORE_SRC) $(INCDIR)/hera_store.h
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -DHERA_SABOTAJE=0 -I$(INCDIR) \
	  $(STORE_SRC) tools/hera_store_test.c -o $@ -lpthread

sabotaje: $(STORE_TEST) auditar
	@$(STORE_TEST) > /dev/null || (echo "FALLO: la bateria no pasa en limpio"; exit 1)
	@echo "limpio: 0 fallos"
	@fallos=0; \
	for n in $(SABOTAJES); do \
	  if ! $(CC) $(CFLAGS) -DHERA_SABOTAJE=$$n -I$(INCDIR) $(STORE_SRC) \
	       tools/hera_store_test.c -lpthread -o $(BINDIR)/hera_st_$$n 2>/dev/null; then \
	    echo "  sabotaje $$n: NO COMPILA"; fallos=1; continue; \
	  fi; \
	  salida=`$(BINDIR)/hera_st_$$n --sabotaje $$n 2>&1`; codigo=$$?; \
	  if [ $$codigo -ne 0 ]; then \
	    echo "  sabotaje $$n: EL BINARIO MURIO (codigo $$codigo)"; fallos=1; \
	  elif ! echo "$$salida" | grep -q "se detecta"; then \
	    echo "  sabotaje $$n: NO SE DETECTA"; fallos=1; \
	  else \
	    echo "  sabotaje $$n: `echo "$$salida" | grep -o 'se detecta ([0-9]* fallos)'`"; \
	  fi; \
	done; \
	if [ $$fallos -ne 0 ]; then \
	  echo "FALLO: algun sabotaje no quedo demostrado"; exit 1; \
	fi; \
	echo "los $(words $(SABOTAJES)) sabotajes se detectan"

mente-test: $(MENTE_TEST)

$(MENTE_TEST): tools/hera_mente_test.c $(MENTE_SRC) $(STORE_SRC)
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -DHERA_SABOTAJE=0 -I$(INCDIR) \
	  $(STORE_SRC) $(MENTE_SRC) tools/hera_mente_test.c -o $@ -lpthread

sabotaje-mente: $(MENTE_TEST)
	@$(MENTE_TEST) > /dev/null || (echo "FALLO: la bateria de la mente no pasa en limpio"; exit 1)
	@echo "limpio: 0 fallos"
	@fallos=0; \
	for n in $(MENTE_SABOTAJES); do \
	  if ! $(CC) $(CFLAGS) -DHERA_SABOTAJE=$$n -I$(INCDIR) $(STORE_SRC) \
	       $(MENTE_SRC) tools/hera_mente_test.c -lpthread -o $(BINDIR)/hera_mt_$$n 2>/dev/null; then \
	    echo "  sabotaje $$n: NO COMPILA"; fallos=1; continue; \
	  fi; \
	  salida=`$(BINDIR)/hera_mt_$$n --sabotaje $$n 2>&1`; codigo=$$?; \
	  if [ $$codigo -ne 0 ]; then \
	    echo "  sabotaje $$n: EL BINARIO MURIO (codigo $$codigo)"; fallos=1; \
	  elif ! echo "$$salida" | grep -q "se detecta"; then \
	    echo "  sabotaje $$n: NO SE DETECTA"; fallos=1; \
	  else \
	    echo "  sabotaje $$n: `echo "$$salida" | grep -o 'se detecta ([0-9]* fallos)'`"; \
	  fi; \
	done; \
	if [ $$fallos -ne 0 ]; then echo "FALLO: algun sabotaje no quedo demostrado"; exit 1; fi; \
	echo "los $(words $(MENTE_SABOTAJES)) sabotajes de la mente se detectan"

cli: $(BINDIR)/hera

$(BINDIR)/hera: tools/hera_cli.c $(STORE_SRC) $(MENTE_SRC)
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -DHERA_SABOTAJE=0 -I$(INCDIR) \
	  $(STORE_SRC) $(MENTE_SRC) tools/hera_cli.c -o $@ -lpthread

# ============================================================================
# La carrera multiproceso no se puede probar dentro de un binario: hacen falta
# procesos de verdad peleandose por el mismo diario. Se lanzan 24 `hera dijo`
# a la vez contra el almacen bueno y contra uno sin cerrojo, y se exige que el
# bueno de 24 ids unicos y que el saboteado NO lo consiga. Si el saboteado
# tambien pasara, la prueba no estaria probando el cerrojo.
# ============================================================================

sabotaje-carrera: cli auditar
	@$(CC) $(CFLAGS) -DHERA_SABOTAJE=10 -I$(INCDIR) $(STORE_SRC) $(MENTE_SRC) \
	  tools/hera_cli.c -lpthread -o $(BINDIR)/hera_sin_cerrojo 2>/dev/null
	@$(MAKE) --no-print-directory carrera BIN=$(BINDIR)/hera        ESPERA=si
	@$(MAKE) --no-print-directory carrera BIN=$(BINDIR)/hera_sin_cerrojo ESPERA=no

# Una tirada de concurrencia sobre el mismo diario, en dos fases:
#
#   fase 1: 24 `dijo` en paralelo            -> ids uN
#   fase 2: UN `dijo` con todos los valores, y luego 24 `guarda` en paralelo
#           citandolo                        -> ids fN
#
# La fase 2 necesita una evidencia SECUENCIAL: con las 24 en paralelo no se
# sabe que texto quedo en que id, asi que ninguna cita cuadraba y salian CERO
# hechos... y la puerta pasaba igual. Por eso ahora se exige el recuento: 24
# hechos escritos, no "los que sean".
#
# ESPERA=si -> 24 uN y 24 fN unicos, diario entero.
# ESPERA=no -> algun id repetido; si no, la prueba no prueba nada.
carrera:
	@d=`mktemp -d`; \
	for i in `seq 1 24`; do HELIOS_HOME=$$d $(BIN) dijo "frase numero $$i" >/dev/null & done; wait; \
	ev=`HELIOS_HOME=$$d $(BIN) dijo "guarda esto: Rufo1 Rufo2 Rufo3 Rufo4 Rufo5 Rufo6 Rufo7 Rufo8 Rufo9 Rufo10 Rufo11 Rufo12 Rufo13 Rufo14 Rufo15 Rufo16 Rufo17 Rufo18 Rufo19 Rufo20 Rufo21 Rufo22 Rufo23 Rufo24"`; \
	for i in `seq 1 24`; do \
	  HELIOS_HOME=$$d $(BIN) guarda "yo/mote$$i" "Rufo$$i" "Le llaman Rufo$$i" $$ev >/dev/null & \
	done; wait; \
	u=`grep -o '"id":"u[0-9]*"' $$d/hera.jsonl | sort -u | wc -l`; \
	f=`grep -o '"id":"f[0-9]*"' $$d/hera.jsonl | sort -u | wc -l`; \
	nu=`grep -c '"r":"dijo"' $$d/hera.jsonl`; \
	nf=`grep -c '"r":"hecho"' $$d/hera.jsonl`; \
	rotas=`grep -cv '}$$' $$d/hera.jsonl || true`; \
	rm -rf $$d; \
	echo "  `basename $(BIN)`: $$nu dijo/$$u ids · $$nf hechos/$$f ids · $$rotas lineas rotas"; \
	if [ "$$nf" != "24" ]; then \
	  echo "  FALLO: se escribieron $$nf hechos y no 24 — la fase 2 no esta probando nada"; exit 1; fi; \
	if [ "$(ESPERA)" = "si" ]; then \
	  if [ "$$u" != "$$nu" ] || [ "$$f" != "$$nf" ] || [ "$$rotas" != "0" ]; then \
	    echo "  FALLO: con cerrojo se repitio algun id o se rompio el diario"; exit 1; fi; \
	  echo "  con cerrojo: 24+1 evidencias y 24 hechos, todos con id unico"; \
	else \
	  if [ "$$u" = "$$nu" ] && [ "$$f" = "$$nf" ]; then \
	    echo "  FALLO: sin cerrojo tambien salen todos unicos — la prueba no prueba nada"; exit 1; fi; \
	  echo "  sin cerrojo: la carrera se reproduce"; \
	fi

auditar:
	@python3 tools/auditar_cerrojos.py src/hera_store.c
