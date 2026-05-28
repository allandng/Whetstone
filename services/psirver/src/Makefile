CXXFLAGS = -std=c++17 -Wall -Wextra -Wpedantic -g -fPIC -fstack-protector-all -pthread
LDFLAGS = -pthread
OBJS = psirver.o utils.o Tasks.o TaskFactory.o Jobs.o
BIN = ./psirver # The main binary

all: $(BIN)

include DEPEND

$(BIN): $(OBJS)
	$(CXX) -o $(BIN) $(OBJS) $(LDFLAGS)

.cc.o:
	$(CXX) $(CXXFLAGS) -c $<

clean:
	rm -f $(BIN) $(OBJS) DEPEND

DEPEND:
	$(CXX) -MM *.cc > DEPEND

test:
	@./test.sh
#END
