import time

from grassroots import * 

class Timing(Blade):
    """Test class"""
    times = Field([])
    number = Field(1)

    @CallableField
    def time(self):
        t = time.time()
        self.times.append(t)
        return t

    @PropertyField
    def deltas(self):
        return map(lambda x, y: x - y, self.times[:-1], self.times[1:])


if __name__ == "__main__":
    root = Root()
    tm = Timing()
    run(root)
