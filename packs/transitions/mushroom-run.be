# @name Mushroom Run
# @desc Mario hits a question block, grabs a mushroom, grows, and runs past a green pipe beneath a bright 8-bit sky.
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

  def draw_cloud(x, y)
    pixel(x + 1, y, 0xFFFFFF)
    pixel(x + 2, y, 0xFFFFFF)
    pixel(x + 3, y, 0xFFFFFF)
    pixel(x, y + 1, 0xFFFFFF)
    pixel(x + 1, y + 1, 0xFFFFFF)
    pixel(x + 2, y + 1, 0xFFFFFF)
    pixel(x + 3, y + 1, 0xFFFFFF)
    pixel(x + 4, y + 1, 0xFFFFFF)
    pixel(x + 1, y + 2, 0xD9F1FF)
    pixel(x + 2, y + 2, 0xD9F1FF)
    pixel(x + 3, y + 2, 0xD9F1FF)
  end

  def draw_brick(x, y)
    rect_fill(x, y, 4, 2, 0xB95727)
    for dx : 0..3 pixel(x + dx, y, 0xE98A3A) end
    pixel(x + 1, y + 1, 0x7D351F)
    pixel(x + 3, y + 1, 0x7D351F)
    pixel(x, y + 1, 0xD97835)
    pixel(x + 2, y + 1, 0xD97835)
  end

  def draw_pipe(x, y)
    rect_fill(x + 1, y, 5, 1, 0x00A64A)
    rect_fill(x, y + 1, 7, 1, 0x00833B)
    rect_fill(x + 1, y + 2, 5, 2, 0x007235)
    rect_fill(x + 2, y + 2, 1, 2, 0x43D86B)
    rect_fill(x + 5, y + 2, 1, 2, 0x005527)
  end

  def draw_background()
    var w = width(), h = height()
    for y : 0..h-3
      var sky = y < 3 ? 0x5C94FC : 0x4384EB
      for x : 0..w-1 pixel(x, y, sky) end
    end

    self.draw_cloud(1, 1)
    self.draw_cloud(w - 12, 0)

    var brick_y = h - 4
    self.draw_brick(2, brick_y)
    self.draw_brick(6, brick_y)
    self.draw_brick(w / 2 + 1, brick_y)
    self.draw_brick(w / 2 + 5, brick_y)

    rect_fill(0, h - 2, w, 1, 0x55B83B)
    rect_fill(0, h - 1, w, 1, 0xA95A2B)
    for x : 0..w-1
      if x % 4 == 0 pixel(x, h - 1, 0x7D3F28) end
      if x % 4 == 2 pixel(x, h - 1, 0xD37A35) end
    end

    self.draw_pipe(w - 6, h - 5)
  end

  def draw_question_block(elapsed)
    var x = width() / 2 - 5
    var bump = elapsed >= 1120 && elapsed < 1450 ? 1 : 0
    var y = height() - 8 - bump
    rect_fill(x, y, 4, 3, 0xF4A623)
    for dx : 0..3 pixel(x + dx, y, 0xFFE15A) end
    pixel(x, y + 1, 0xD17A1C)
    pixel(x + 3, y + 1, 0xD17A1C)
    pixel(x, y + 2, 0xD17A1C)
    pixel(x + 3, y + 2, 0xD17A1C)
    pixel(x + 1, y, 0x9A461D)
    pixel(x + 2, y, 0x9A461D)
    pixel(x + 2, y + 1, 0x9A461D)
    pixel(x + 1, y + 2, 0xFFF4B0)
  end

  def draw_mushroom(x, y)
    pixel(x + 1, y, 0xE52521)
    pixel(x, y + 1, 0xE52521)
    pixel(x + 1, y + 1, 0xFFFFFF)
    pixel(x + 2, y + 1, 0xE52521)
    pixel(x, y + 2, 0xF4D9AE)
    pixel(x + 1, y + 2, 0xF4D9AE)
    pixel(x + 2, y + 2, 0xF4D9AE)
  end

  def draw_small_mario(x, y, gait)
    var red = 0xE52521, skin = 0xFFC18B, brown = 0x6D321F, blue = 0x2454D8
    pixel(x + 1, y, red)
    pixel(x + 2, y, red)
    pixel(x + 3, y, red)
    pixel(x + 4, y, red)
    pixel(x, y + 1, brown)
    pixel(x + 1, y + 1, red)
    pixel(x + 2, y + 1, red)
    pixel(x + 3, y + 1, red)
    pixel(x + 4, y + 1, red)
    pixel(x, y + 2, brown)
    pixel(x + 1, y + 2, skin)
    pixel(x + 2, y + 2, skin)
    pixel(x + 3, y + 2, skin)
    pixel(x + 4, y + 2, skin)
    pixel(x + 1, y + 3, brown)
    pixel(x + 2, y + 3, skin)
    pixel(x + 3, y + 3, skin)
    pixel(x + 4, y + 3, skin)
    pixel(x, y + 4, gait == 0 ? brown : blue)
    pixel(x + 1, y + 4, blue)
    pixel(x + 2, y + 4, blue)
    pixel(x + 3, y + 4, blue)
    pixel(x + 4, y + 4, gait == 0 ? blue : brown)
  end

  def draw_big_mario(x, y, gait)
    var red = 0xE52521, skin = 0xFFC18B, brown = 0x6D321F, blue = 0x2454D8
    pixel(x + 1, y, red)
    pixel(x + 2, y, red)
    pixel(x + 3, y, red)
    pixel(x + 4, y, red)
    pixel(x + 5, y, red)
    pixel(x, y + 1, brown)
    pixel(x + 1, y + 1, red)
    pixel(x + 2, y + 1, red)
    pixel(x + 3, y + 1, red)
    pixel(x + 4, y + 1, red)
    pixel(x + 5, y + 1, red)
    pixel(x, y + 2, brown)
    pixel(x + 1, y + 2, skin)
    pixel(x + 2, y + 2, skin)
    pixel(x + 3, y + 2, skin)
    pixel(x + 4, y + 2, skin)
    pixel(x + 5, y + 2, skin)
    pixel(x, y + 3, brown)
    pixel(x + 1, y + 3, skin)
    pixel(x + 2, y + 3, skin)
    pixel(x + 3, y + 3, brown)
    pixel(x + 4, y + 3, skin)
    pixel(x + 5, y + 3, skin)
    pixel(x, y + 4, red)
    pixel(x + 1, y + 4, red)
    pixel(x + 2, y + 4, blue)
    pixel(x + 3, y + 4, blue)
    pixel(x + 4, y + 4, blue)
    pixel(x + 5, y + 4, red)
    pixel(x + 1, y + 5, blue)
    pixel(x + 2, y + 5, 0xF7D14A)
    pixel(x + 3, y + 5, blue)
    pixel(x + 4, y + 5, blue)
    if gait == 0
      pixel(x, y + 6, brown)
      pixel(x + 1, y + 6, brown)
      pixel(x + 4, y + 6, brown)
      pixel(x + 5, y + 6, brown)
    else
      pixel(x, y + 6, brown)
      pixel(x + 1, y + 6, brown)
      pixel(x + 3, y + 6, brown)
      pixel(x + 4, y + 6, brown)
      pixel(x + 5, y + 6, brown)
    end
  end

  def draw_sparkles(x, y, elapsed)
    var color = elapsed % 140 < 70 ? 0xFFF36A : 0xFFFFFF
    pixel(x - 1, y + 2, color)
    pixel(x + 6, y + 1, color)
    pixel(x + 3, y - 1, color)
    pixel(x + 5, y + 5, color)
  end

  def draw()
    var elapsed = (now_ms() - self.started) % self.ms
    var timeline = int(elapsed * 7000 / self.ms)
    var wait_x = width() / 2 - 9
    var grown_x = wait_x + 6
    self.draw_background()
    self.draw_question_block(timeline)

    var mario_x = -7, jump = 0
    if timeline < 1000
      mario_x = -7 + int(timeline * (wait_x + 7) / 1000)
    elif timeline < 1800
      mario_x = wait_x
      if timeline >= 1120 && timeline < 1450 jump = -1 end
    elif timeline < 3100
      mario_x = wait_x
    elif timeline < 4000
      mario_x = wait_x + int((timeline - 3100) * 6 / 900)
    elif timeline < 4300
      mario_x = grown_x
    else
      mario_x = grown_x + int((timeline - 4300) * (width() + 4 - grown_x) / 2100)
    end

    if timeline >= 1700 && timeline < 4000
      var mushroom_x = width() / 2 - 4, mushroom_y = height() - 10
      if timeline < 2400
        mushroom_y = height() - 10 + int((timeline - 1700) * 6 / 700)
      else
        mushroom_x += int((timeline - 2400) * 5 / 1600)
        mushroom_y = height() - 4
      end
      self.draw_mushroom(mushroom_x, mushroom_y)
    end

    var gait = int(timeline / 140) % 2
    if timeline < 4200
      self.draw_small_mario(mario_x, height() - 6 + jump, gait)
    else
      self.draw_big_mario(mario_x, height() - 8, gait)
    end

    if timeline >= 3850 && timeline < 4500
      self.draw_sparkles(mario_x, height() - 7, timeline)
    end
  end
end

return App()
