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

ALL_SRC = $(CORE_SRC) $(STORE_SRC)

# Object files
OBJECTS = $(patsubst $(SRCDIR)/%.c,$(OBJDIR)/%.o,$(ALL_SRC))

# Library target
LIB_TARGET = $(BINDIR)/libhera.a

# Test target
TEST_TARGET = $(BINDIR)/hera_test

# ============================================================================
# Rules
# ============================================================================

.PHONY: all clean lib test store-test sabotaje

all: lib test store-test

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

store-test: $(STORE_TEST)

$(STORE_TEST): tools/hera_store_test.c $(STORE_SRC) $(INCDIR)/hera_store.h
	@mkdir -p $(BINDIR)
	$(CC) $(CFLAGS) -DHERA_SABOTAJE=0 -I$(INCDIR) \
	  $(STORE_SRC) tools/hera_store_test.c -o $@

sabotaje: $(STORE_TEST)
	@$(STORE_TEST) > /dev/null || (echo "FALLO: la bateria no pasa en limpio"; exit 1)
	@echo "limpio: 0 fallos"
	@fallos=0; \
	for n in $(SABOTAJES); do \
	  if ! $(CC) $(CFLAGS) -DHERA_SABOTAJE=$$n -I$(INCDIR) $(STORE_SRC) \
	       tools/hera_store_test.c -o $(BINDIR)/hera_st_$$n 2>/dev/null; then \
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
