# @name Ghost Parade
# @desc Red, pink, cyan, and orange arcade ghosts march across a glowing full-screen backdrop.
# @author Deskmate
# @version 1.0.0
# @display 32x8
# @config durationMs number "Duration" default=7000 min=1000 max=7000 step=100 unit=ms

class App
  var started, ms, background

  def init()
    self.started = now_ms()
    self.ms = self.duration()
    self.background = [0x100B35, 0x160C42, 0x210D4C, 0x2B1050,
                       0x35104B, 0x250E47, 0x190D40, 0x120C38]
  end

  def duration()
    var value = int(store.get('durationMs'))
    if value < 1000 value = 1000 end
    if value > 7000 value = 7000 end
    return value
  end

  def on_show()
    self.started = now_ms()
    self.ms = self.duration()
  end

  def draw_ghost(x, color, gait)
    pixel(x + 2, 0, color)
    pixel(x + 3, 0, color)
    pixel(x + 4, 0, color)
    for dx : 1..5 pixel(x + dx, 1, color) end
    for dx : 0..6 pixel(x + dx, 2, color) end

    pixel(x, 3, color)
    pixel(x + 1, 3, 0xFFFFFF)
    pixel(x + 2, 3, 0x1200D8)
    pixel(x + 3, 3, color)
    pixel(x + 4, 3, 0xFFFFFF)
    pixel(x + 5, 3, 0x1200D8)
    pixel(x + 6, 3, color)

    pixel(x, 4, color)
    pixel(x + 1, 4, 0xFFFFFF)
    pixel(x + 2, 4, 0xFFFFFF)
    pixel(x + 3, 4, color)
    pixel(x + 4, 4, 0xFFFFFF)
    pixel(x + 5, 4, 0xFFFFFF)
    pixel(x + 6, 4, color)
    for dx : 0..6 pixel(x + dx, 5, color) end

    pixel(x, 6, color)
    pixel(x + 3, 6, color)
    pixel(x + 6, 6, color)
    if gait == 0
      pixel(x + 1, 6, color)
      pixel(x + 4, 6, color)
    else
      pixel(x + 2, 6, color)
      pixel(x + 5, 6, color)
    end
  end

  def draw()
    var elapsed = now_ms() - self.started
    var shimmer = int(elapsed * 100 / self.ms) % 16
    for y : 0..7
      for x : 0..31
        var color = self.background[y] + (shimmer << 8)
        pixel(x, y, color)
      end
    end

    var offset = int(elapsed * 63 / self.ms) - 31
    var gait = int(elapsed / 180) % 2
    self.draw_ghost(offset, 0xE92738, gait)
    self.draw_ghost(offset + 8, 0xF38CEB, gait)
    self.draw_ghost(offset + 16, 0x00DCE8, gait)
    self.draw_ghost(offset + 24, 0xFFB84D, gait)
  end
end

return App()
