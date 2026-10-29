"""测试里代替真实键鼠注入的记录器。"""


class RecordingInjector:
    def __init__(self) -> None:
        self.events = []

    def move(self, dx, dy) -> None:
        self.events.append(("move", dx, dy))

    def button(self, name, down) -> None:
        self.events.append(("button", name, down))

    def scroll(self, dx, dy) -> None:
        self.events.append(("scroll", dx, dy))

    def key(self, spec, down) -> None:
        self.events.append(("key", spec["kind"], spec["v"], down))

    def release_all(self) -> None:
        self.events.append(("release_all",))
