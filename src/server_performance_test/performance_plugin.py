import random
import math
import time
import psutil
from endstone.plugin import Plugin
from endstone.event import event_handler, PlayerInteractEvent
from endstone import ColorFormat

class PerformancePlugin(Plugin):
    api_version = "0.5"
    broadcast_interval = 5.0 # 5초 주기
    last_click = {}
    _performance_task_id = None # 주기적인 스케줄러 작업을 위한 ID 저장

    def on_enable(self) -> None:
        self.logger.info("PerformancePlugin 활성화됨: TNT 소환 및 서버 상태 전송 시작")
        self.register_events(self)

        # Scheduler 객체가 어떤 메서드를 가지고 있는지 확인하기 위한 코드 (이미 확인됨)
        # self.logger.info(f"Scheduler 객체의 사용 가능한 속성: {dir(self.server.scheduler)}")

        # Endstone의 스케줄러를 사용하여 성능 브로드캐스트 작업을 예약합니다.
        # run_task_timer 대신 run_task를 사용하여 주기적으로 자신을 다시 예약합니다.
        try:
            # 첫 실행은 지연 없이 즉시 실행
            self._performance_task_id = self.server.scheduler.run_task(self, self._broadcast_performance)
            self.logger.info(f"성능 브로드캐스트 작업이 예약되었습니다 (run_task 사용).")
        except AttributeError as e:
            self.logger.error(f"스케줄러 작업 예약 중 오류 발생: {e}")
            self.logger.error("Endstone의 Scheduler 객체에 run_task_timer/run_task가 없는 것으로 보입니다.")

    def on_disable(self) -> None:
        # 이전에 예약된 작업이 있다면 취소합니다.
        if self._performance_task_id:
            try:
                self.server.scheduler.cancel_task(self._performance_task_id)
            except AttributeError as e:
                self.logger.error(f"스케줄러 작업 취소 중 오류 발생 (Scheduler.cancel_task 없음?): {e}")
            self._performance_task_id = None
        self.logger.info("PerformancePlugin 비활성화됨")

    def _broadcast_performance(self):
        """
        주기적으로 서버 성능 지표를 수집하고 OP 플레이어에게 전송합니다.
        run_task로 실행되므로, 주기적인 실행을 위해 내부에서 다음 작업을 다시 예약합니다.
        """
        srv = self.server

        # 서버 성능 지표 수집
        tps = srv.current_tps
        players = len(srv.online_players)
        mspt = srv.current_mspt
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent

        msg = (
            f"{ColorFormat.GREEN}TPS:{tps:.1f} Players:{players}명 | "
            f"CPU:{cpu:.1f}% RAM:{ram:.1f}% MSPT:{mspt:.2f}ms"
        )

        for p in srv.online_players:
            if p.has_permission("op"):
                # PacketSendEvent must be triggered synchronously from server thread 오류를 방지하기 위해
                # 플레이어에게 메시지를 보내는 작업을 메인 스레드에서 실행하도록 보장합니다.
                # run_task는 기본적으로 메인 스레드에서 실행되므로 이 방식은 안전합니다.
                p.send_message(msg)

        # 다음 브로드캐스트 작업을 다시 예약합니다.
        # delay는 틱(tick) 단위이며, 1초는 약 20틱입니다.
        # 이전에 _performance_task_id에 저장된 ID는 현재 실행 중인 작업의 ID이므로,
        # 새로운 작업을 예약하기 전에 필요하다면 현재 작업을 취소할 수 있으나,
        # run_task는 기본적으로 단일 실행이므로 이 부분은 단순화될 수 있습니다.
        # 여기서는 단순히 다음 작업을 예약하고, 새 ID를 저장합니다.
        try:
            self._performance_task_id = self.server.scheduler.run_task(
                self,
                self._broadcast_performance,
                delay=int(self.broadcast_interval * 20)
            )
        except AttributeError as e:
            self.logger.error(f"다음 스케줄러 작업 예약 중 오류 발생: {e}")


    @event_handler
    def on_player_interact(self, event: PlayerInteractEvent) -> None:
        if event.block is None or event.item is None:
            return
        player = event.player
        if not player.has_permission("op") or not player.is_sneaking:
            return

        # 디바운스(0.5초)
        uid = player.xuid
        now = time.time()
        last = self.last_click.get(uid)
        if last and (now - last) < 0.5:
            return
        self.last_click[uid] = now

        if event.item.type != "minecraft:blaze_rod":
            return

        # TNT 소환 (4~8개)
        loc = player.location
        count = random.randint(4, 8)
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(3, 10)
            height = random.uniform(2, 8)
            x = loc.x + math.cos(angle) * dist
            y = loc.y + height
            z = loc.z + math.sin(angle) * dist # TNT 소환 Z 좌표 계산
            self.server.dispatch_command(
                self.server.command_sender,
                f"summon tnt {x:.2f} {y:.2f} {z:.2f}"
            )
        player.send_message(f"{ColorFormat.YELLOW}{count}개의 TNT 소환 완료!")
        self.logger.info(f"{player.name}이 {count}개의 TNT 소환")