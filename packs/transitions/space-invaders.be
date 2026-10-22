# @name Space Invaders
# @desc A pixel spaceship sweeps beneath a descending invader wave, firing until the screen clears.
# @author Deskmate
# @version 1.0.0
# @display 32x8
# @config durationMs number "Duration" default=7000 min=1000 max=7000 step=100 unit=ms

class App
  var started, ms, targets

  def init()
    self.started = now_ms()
    self.ms = self.duration()
    self.targets = [0, 1, 2, 2, 1, 0]
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

  def draw_invader(x, y, color, gait)
    pixel(x + 1, y, color)
    pixel(x + 3, y, color)
    for dx : 0..4 pixel(x + dx, y + 1, color) end
    pixel(x, y + 2, color)
    pixel(x + 2, y + 2, color)
    pixel(x + 4, y + 2, color)
    if gait == 1
      pixel(x + 1, y + 2, color)
      pixel(x + 3, y + 2, color)
    end
  end

  def draw_ship(x)
    pixel(x + 2, 6, 0xFFFFFF)
    pixel(x, 7, 0x00DDF5)
    pixel(x + 1, 7, 0x00DDF5)
    pixel(x + 2, 7, 0xFFFFFF)
    pixel(x + 3, 7, 0x00DDF5)
    pixel(x + 4, 7, 0x00DDF5)
  end

  def draw_explosion(cx, cy, phase)
    var color = phase < 50 ? 0xFFF27A : 0xFF7228
    pixel(cx, cy, 0xFFFFFF)
    pixel(cx - 1, cy, color)
    pixel(cx + 1, cy, color)
    pixel(cx, cy - 1, color)
    pixel(cx, cy + 1, color)
    if phase < 55
      pixel(cx - 2, cy - 1, 0xFFB331)
      pixel(cx + 2, cy + 1, 0xFFB331)
      pixel(cx + 2, cy - 1, 0xFFB331)
      pixel(cx - 2, cy + 1, 0xFFB331)
    end
  end

  def draw()
    var elapsed = (now_ms() - self.started) % self.ms
    var timeline = int(elapsed * 7000 / self.ms)
    var gait = int(timeline / 180) % 2
    clear()

    if timeline < 450
      var y = -2 + int(timeline * 2 / 450)
      var offset = int(timeline * 2 / 450)
      for i : 0..5
        var row = int(i / 3), col = i % 3
        var color = row == 0 ? 0x75F04B : 0x42DDAA
        self.draw_invader(1 + col * 10 + offset, y + row * 3, color, gait)
      end
      self.draw_ship(13)
    elif timeline < 4050
      var battle = timeline - 450
      var slot = int(battle / 600), within = battle % 600
      var swing = int(battle / 280) % 8
      var offset = swing <= 4 ? swing : 8 - swing
      var descent = int(battle / 1800)
      var target_col = self.targets[slot]
      var target_x = 3 + target_col * 10 + offset
      var previous_col = slot == 0 ? 1 : self.targets[slot - 1]
      var previous_x = 3 + previous_col * 10 + offset
      var ship_center = target_x
      if within < 300
        ship_center = previous_x + int((target_x - previous_x) * within / 300)
      end

      for i : 0..5
        var row = int(i / 3), col = i % 3
        var x = 1 + col * 10 + offset
        var y = descent + row * 3
        var color = row == 0 ? 0x75F04B : 0x42DDAA
        if i > slot || (i == slot && within < 460)
          self.draw_invader(x, y, color, gait)
        elif i == slot && within < 560
          self.draw_explosion(x + 2, y + 1, within - 460)
        end
      end

      if within >= 300 && within < 460
        var target_y = descent + int(slot / 3) * 3 + 1
        var bullet_y = 6 - int((within - 300) * (6 - target_y) / 160)
        pixel(ship_center, bullet_y, 0xFFFFFF)
        if bullet_y < 6 pixel(ship_center, bullet_y + 1, 0xFFD53D) end
      end
      self.draw_ship(ship_center - 2)
    elif timeline < 4700
      var ship_x = 1 + int((timeline - 4050) * 26 / 650)
      self.draw_ship(ship_x)
    else
      var remaining = 2300 - (timeline - 4700)
      var y = -2 - int(remaining * 2 / 2300)
      var offset = int(remaining * 4 / 2300)
      for i : 0..5
        var row = int(i / 3), col = i % 3
        var color = row == 0 ? 0x75F04B : 0x42DDAA
        self.draw_invader(1 + col * 10 + offset, y + row * 3, color, gait)
      end
      self.draw_ship(13)
    end
  end
end

return App()
