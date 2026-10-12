# @name Vampire Awakens
# @desc A cloaked vampire wakes beneath a blood moon as bats take flight.
# @author Deskmate
# @version 1.1.0
# @display 32x8
# @config durationMs number "Duration" default=5000 min=1000 max=5000 step=100 unit=ms

import math

class App
  var started, ms
  def init()
    self.started = now_ms()
    self.ms = 0
  end
  def duration()
    var ms = int(store.get("durationMs"))
    if ms < 1000 ms = 1000 elif ms > 5000 ms = 5000 end
    return ms
  end
  def on_show()
    self.started = now_ms()
    self.ms = self.duration()
  end
  def bat(x,y,color)
    pixel(x,y,color)
    pixel(x-1,y,color)
    pixel(x+1,y,color)
    pixel(x-2,y-1,color)
    pixel(x-3,y-1,color)
    pixel(x-2,y,color)
    pixel(x+2,y-1,color)
    pixel(x+3,y-1,color)
    pixel(x+2,y,color)
  end
  def draw()
    clear(0x07091D)
    var t = (now_ms() - self.started) * 1.0 / self.ms
    if t < 0 t = 0 end
    if t >= 1 return end

    # A pale moon and low castle establish the gothic night.
    rect_fill(25,0,3,1,0xDDF8F5)
    rect_fill(24,1,5,3,0xDDF8F5)
    rect_fill(25,4,3,1,0xDDF8F5)
    rect_fill(26,1,3,3,0x07091D)
    pixel(4,1,0x6F78A8)
    pixel(8,2,0x6F78A8)
    pixel(20,1,0x6F78A8)
    rect_fill(0,6,32,2,0x100E28)
    rect_fill(2,5,4,2,0x100E28)
    rect_fill(4,4,1,2,0x100E28)
    rect_fill(8,5,3,2,0x100E28)
    rect_fill(9,4,1,2,0x100E28)
    rect_fill(22,5,4,2,0x100E28)
    rect_fill(23,4,1,2,0x100E28)
    pixel(3,6,0xF04B5F)
    pixel(9,6,0xF04B5F)
    pixel(24,6,0xF04B5F)

    # The cloak rises in the second beat, then sinks back into the scene.
    var reveal = clamp((t-0.12)/0.20,0,1)
    var vanish = clamp((t-0.84)/0.16,0,1)
    if reveal > 0.05 && vanish < 0.95
      var cloak_y = 7 - int(reveal * 3)
      var cloak = 0x31205F
      var edge = 0x8E2B83
      line(15,cloak_y,15,7,cloak)
      line(16,cloak_y,16,7,cloak)
      line(14,cloak_y+1,17,7,cloak)
      line(13,cloak_y+2,18,7,cloak)
      line(12,cloak_y+3,19,7,cloak)
      pixel(15,cloak_y-1,edge)
      pixel(16,cloak_y-1,edge)
      if t > 0.28 && t < 0.76
        var eye = 0xF04B5F
        if t > 0.43 && t < 0.55 eye = 0xFF8A5C end
        pixel(14,cloak_y+1,eye)
        pixel(17,cloak_y+1,eye)
      end
    end

    # Three bats launch at staggered times and arc across the moon.
    var i = 0
    while i < 3
      var launch = 0.34 + i * 0.09
      var p = (t-launch)/0.38
      if p > 0 && p < 1
        var bx = -2 + int(p*36) + i*2
        var by = 2 + int(math.sin((p+i)*6.2)*1.0) + i
        self.bat(bx,by,0xA855F7)
      end
      i += 1
    end
  end
end

return App()
