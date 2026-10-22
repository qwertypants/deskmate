# @name NYC After Dark
# @desc Stars and drifting clouds reveal a glowing Manhattan skyline rising into the night.
# @author Deskmate
# @version 1.0.0
# @display 32x8
# @config durationMs number "Duration" default=7000 min=1000 max=7000 step=100 unit=ms

class App
  var started, ms

  def init()
    self.started = now_ms()
    self.ms = self.duration()
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

  def draw_cloud(x, y, color)
    for dx : 0..5 pixel(x + dx, y, color) end
    for dx : 1..4 pixel(x + dx, y - 1, color) end
  end

  def draw()
    var elapsed = (now_ms() - self.started) % self.ms
    var phase = int(elapsed / 180)
    clear()

    # Deep violet at the horizon fades into an ink-blue upper sky.
    for y : 0..7
      var r = 4 + y * 2
      var g = 8 + y * 2
      var b = 29 + y * 5
      var color = (r << 16) | (g << 8) | b
      for x : 0..31 pixel(x, y, color) end
    end

    # Most stars stay faint; a few brighten slightly at staggered intervals.
    var starsX = [2, 7, 12, 18, 24, 29, 4, 21]
    var starsY = [1, 0, 2, 1, 0, 2, 3, 3]
    for i : 0..7
      var twinkle = (phase + i * 5) % 31
      var color = twinkle < 4 ? 0x8493A9 : 0x5B6A82
      pixel(starsX[i], starsY[i], color)
    end

    # Flat stepped cloud bands drift slowly across the upper sky.
    var cloudA = (phase / 2) % 38 - 6
    var cloudB = 25 - (phase / 3) % 38
    self.draw_cloud(cloudA, 2, 0x35466E)
    self.draw_cloud(cloudB, 4, 0x293B61)

    # Separate broad building masses read as a skyline at native resolution.
    # The skyline and window lights stay fixed while the clouds drift overhead.
    # The central Empire State Building has a stepped crown and narrow spire.
    var baseY = 0
    var left = [0, 5, 10, 14, 20, 25, 29]
    var right = [3, 8, 12, 18, 23, 27, 31]
    var roof = [5, 4, 5, 2, 4, 3, 5]
    for building : 0..6
      for x : left[building]..right[building]
        var top = roof[building]
        # Step the Empire State crown inward toward its mast.
        if building == 3 && (x == 14 || x == 18) top = 3 end
        for y : top..7
          if y >= baseY
            var facade = y == top ? 0x34425C : 0x202A40
            pixel(x, y, facade)
            var window = ((x + building) % 2 == 0) && ((y + building) % 2 == 0)
            if window && ((x * 3 + y * 5) % 7 < 4)
              pixel(x, y, ((x + y) % 3 == 0) ? 0xD99A55 : 0xA96C45)
            end
          end
        end
      end
    end
    # Empire State Building mast and illuminated crown.
    if baseY <= 2
      pixel(16, 0, 0xC1A574)
      pixel(15, 1, 0xB58E5B)
      pixel(16, 1, 0xC1A574)
      pixel(17, 1, 0xB58E5B)
      pixel(15, 2, 0x9E744B)
      pixel(16, 2, 0xC1A574)
      pixel(17, 2, 0x9E744B)
    end
  end
end

return App()
