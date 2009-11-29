 
CFLAGS="-O0 -Wall"
CFLAGS="-O3 -Wall"

sources = lm.cpp lm_dynamic.cpp lm_python.cpp

lm.so : $(sources)
	CFLAGS=$(CFLAGS) python setup.py build
	cp ./build/lib.*/lm.so .

Debug : lm.so

.PHONY : clean
clean :
	python setup.py clean
	-rm lm.so
	-rm -rf ./build

install:
	python setup.py install
	
