


all:
	@echo 'make test'
	@echo 'make coverage'

.PHONY: test
test:
	micropython test/test_bitstore.py
	micropython test/test_bits.py


coverage:
	coverage3 run test/test_bitstore.py
	coverage3 run test/test_bits.py
	coverage3 report --show-missing --include=ubitstring.py

