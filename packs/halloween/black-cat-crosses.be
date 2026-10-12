# @name Black Cat Crosses
# @desc A sleek black cat slips through the moonlight and disappears.
# @author Deskmate
# @version 1.0.0
# @display 32x8
# @config durationMs number "Duration" default=5000 min=1000 max=5000 step=100 unit=ms

class App
  var started, ms

  def duration()
    var value = int(store.get('durationMs', 5000))
    if value < 1000 value = 1000 end
    if value > 5000 value = 5000 end
    return value
  end

  def on_show()
    self.ms = self.duration()
    self.started = now_ms()
  end

  def moon()
    # A small amber crescent hangs behind the cat at the center of the loop.
    rect_fill(25, 1, 3, 1, 0xFF8A5C)
    rect_fill(24, 2, 4, 3, 0xFF8A5C)
    rect_fill(25, 5, 3, 1, 0xFF8A5C)
    rect_fill(26, 2, 2, 3, 0x100E18)
  end

  def cat(x, y, blink)
    var ink = 0x07091D
    var eye = 0xFFD85A
    # Pointed ears and a compact head.
    pixel(x + 2, y, ink)
    pixel(x + 5, y, ink)
    rect_fill(x + 1, y + 1, 6, 3, ink)
    pixel(x + 2, y + 1, 0x31205F)
    pixel(x + 5, y + 1, 0x31205F)
    if blink
      pixel(x + 2, y + 2, eye)
      pixel(x + 5, y + 2, eye)
    else
      line(x + 2, y + 2, x + 3, y + 2, eye)
      line(x + 5, y + 2, x + 6, y + 2, eye)
    end
    # Back, haunch, belly, and four quick walking legs.
    rect_fill(x + 5, y + 4, 10, 2, ink)
    rect_fill(x + 8, y + 3, 6, 3, ink)
    rect_fill(x + 7, y + 6, 2, 2, ink)
    rect_fill(x + 12, y + 6, 2, 2, ink)
    rect_fill(x + 15, y + 5, 2, 3, ink)
    rect_fill(x + 18, y + 5, 2, 3, ink)
    # Tail gives the silhouette a readable flourish as it crosses.
    line(x + 15, y + 4, x + 19, y + 2, ink)
    line(x + 19, y + 2, x + 21, y + 3, ink)
    if x > 10 && x < 20
      line(x + 19, y + 3, x + 21, y + 1, 0x31205F)
    end
  end

  def draw()
    clear()
    if self.started == nil self.on_show() end
    var t = (now_ms() - self.started) * 1.0 / self.ms
    if t < 0 t = 0 end
    if t >= 1 return end

    if t > 0.10 && t < 0.92
      self.moon()
      var progress = (t - 0.10) / 0.82
      var x = int(-9 + progress * 35)
      var blink = (t > 0.28 && t < 0.34) || (t > 0.68 && t < 0.73)
      self.cat(x, 1, blink)
    elif t >= 0.92
      self.moon()
    end
  end
end

return App()
