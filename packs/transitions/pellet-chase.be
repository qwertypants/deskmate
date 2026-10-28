# @name Pellet Chase
# @desc Pac-Man collects pellets, glows after a power pellet, and chases two frightened ghosts out of a blue maze corridor.
# @author Deskmate
# @version 1.0.0
# @display 32x8
# @config durationMs number "Duration" default=8000 min=1000 max=8000 step=100 unit=ms

class App
  var started, ms

  def init()
    self.started = now_ms()
    self.ms = self.duration()
  end

  def duration()
    return clamp(int(store.get('durationMs')), 1000, 8000)
  end

  def on_show()
    self.started = now_ms()
    self.ms = self.duration()
  end

  # Five-pixel silhouettes leave a black gap between the characters and rails.
  def pacman(x, left, mouth, color)
    for dy : -2..2
      for dx : -2..2
        var ax = dx < 0 ? -dx : dx
        var ay = dy < 0 ? -dy : dy
        if ax + ay <= 3
          var facing = left ? -dx : dx
          if !mouth || facing < 0 || ay > facing
            pixel(x + dx, 3 + dy, color)
          end
        end
      end
    end
  end

  def ghost(x, color, scared, gait)
    rect_fill(x - 1, 1, 3, 1, color)
    rect_fill(x - 2, 2, 5, 3, color)
    for dx : -2..2
      if (dx + gait) % 2 == 0 pixel(x + dx, 5, color) end
    end
    pixel(x - 1, 2, 0xFFFFFF)
    pixel(x + 1, 2, 0xFFFFFF)
    if scared
      pixel(x, 4, 0xB9E9FF)
    else
      pixel(x, 3, 0x101046)
      pixel(x + 2, 3, 0x101046)
    end
  end

  def draw()
    # Normalize pacing so shortened configurations still tell the whole story.
    var t = clamp(int((now_ms() - self.started) * 8000 / self.ms), 0, 7999)
    clear(0)
    line(0, 0, 31, 0, 0x1838C8)
    line(0, 7, 31, 7, 0x1838C8)
    for x : 0..31
      if x % 8 < 5 pixel(x, 6, 0x0C1658) end
    end

    var powered = t >= 5000
    var x = -3 + int(t * 30 / 5000)
    if powered
      x = 27
      if t >= 5400 x = 27 - int((t - 5400) * 34 / 2300) end
    end
    if !powered
      for pellet : 0..5
        var px = 4 + pellet * 4
        if px > x + 1 pixel(px, 3, 0xFFE6B0) end
      end
      var power = int(t / 200) % 2 == 0 ? 0xFFFFFF : 0xFFCE64
      pixel(27, 2, power)
      pixel(26, 3, power)
      pixel(27, 3, power)
      pixel(28, 3, power)
      pixel(27, 4, power)
    end

    var ghostA = x - 8
    var ghostB = x - 15
    if powered
      var retreat = int(max(0, t - 5100) * 38 / 2300)
      ghostA = 19 - retreat
      ghostB = 12 - retreat
    end
    var gait = int(t / 140) % 2
    self.ghost(ghostB, powered ? 0x244CFF : 0xF58CDE, powered, gait)
    self.ghost(ghostA, powered ? 0x244CFF : 0xF23848, powered, gait)

    if powered && x >= -2
      var glow = int(t / 120) % 2 == 0 ? 0x967124 : 0x493512
      pixel(x - 3, 2, glow)
      pixel(x - 3, 4, glow)
      pixel(x + 3, 2, glow)
      pixel(x + 3, 4, glow)
      pixel(x - 1, 6, glow)
      pixel(x + 1, 6, glow)
    end
    var color = powered && int(t / 120) % 2 == 0 ? 0xFFF5B0 : 0xFFDC00
    self.pacman(x, powered, int(t / 120) % 3 != 0, color)
  end
end

return App()
