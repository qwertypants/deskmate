# @name Cat at the Window
# @desc A curious cat rises from the darkness, looks around, and sinks away.
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

  def face(x, y, look, blink)
    var fur = 0x07091D
    var ear = 0xA855F7
    var eye = 0xFFD85A
    # Ears, forehead, cheeks, and a small triangular chin.
    pixel(x + 1, y, fur)
    pixel(x + 2, y + 1, fur)
    pixel(x + 7, y, fur)
    pixel(x + 6, y + 1, fur)
    rect_fill(x + 2, y + 1, 5, 1, fur)
    rect_fill(x + 1, y + 2, 7, 3, fur)
    rect_fill(x + 2, y + 5, 5, 1, fur)
    pixel(x + 2, y + 1, ear)
    pixel(x + 6, y + 1, ear)
    if blink
      line(x + 2, y + 3, x + 3, y + 3, eye)
      line(x + 5, y + 3, x + 6, y + 3, eye)
    else
      rect_fill(x + 2, y + 2, 2, 2, eye)
      rect_fill(x + 5, y + 2, 2, 2, eye)
      pixel(x + 2 + look, y + 3, fur)
      pixel(x + 5 + look, y + 3, fur)
    end
    pixel(x + 4, y + 4, 0xFF8A5C)
    line(x + 1, y + 4, x - 1, y + 3, 0x31205F)
    line(x + 1, y + 5, x - 1, y + 5, 0x31205F)
    line(x + 7, y + 4, x + 9, y + 3, 0x31205F)
    line(x + 7, y + 5, x + 9, y + 5, 0x31205F)
  end

  def draw()
    clear()
    if self.started == nil self.on_show() end
    var t = (now_ms() - self.started) * 1.0 / self.ms
    if t < 0 t = 0 end
    if t >= 1 return end
    if t > 0.08 && t < 0.92
      var y = 8
      if t < 0.28
        y = int(8 - 6 * (t - 0.08) / 0.20)
      elif t < 0.70
        y = 2
      else
        y = int(2 + 6 * (t - 0.70) / 0.22)
      end
      var look = 1
      if t > 0.38 && t < 0.52 look = 0 end
      if t >= 0.52 && t < 0.66 look = 2 end
      var blink = t > 0.30 && t < 0.35
      self.face(12, y, look, blink)
    end
  end
end

return App()
