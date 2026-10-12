# @name Neon Highway
# @desc A retro cyberpunk sunset anchors a luminous highway while cyan and magenta road lines stream toward the viewer.
# @author Deskmate
# @version 1.0.0
# @display 32x8
# @config durationMs number "Duration" default=7000 min=1000 max=7000 step=100 unit=ms

import math

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

  def mix(a, b, amount)
    var ar = (a >> 16) & 255, ag = (a >> 8) & 255, ab = a & 255
    var br = (b >> 16) & 255, bg = (b >> 8) & 255, bb = b & 255
    var r = int(ar + (br - ar) * amount)
    var g = int(ag + (bg - ag) * amount)
    var blue = int(ab + (bb - ab) * amount)
    return (r << 16) | (g << 8) | blue
  end

  def absolute(value)
    return value < 0 ? -value : value
  end

  def draw()
    clear()
    # A fractional phase makes the 7000 ms boundary identical to phase zero.
    var turns = (now_ms() - self.started) * 1.0 / self.ms
    var phase = (turns - int(turns)) * 6.283185307179586
    var w = width(), h = height()
    for y : 0..h-1
      for x : 0..w-1
        var color = 0x16133D
        if y == 0
          color = 0x171344
        elif y == 1
          color = 0x342060
        elif y == 2
          color = 0x6B2C72
        elif y == 3
          color = 0xC24C69
        elif y == 4
          color = 0x311B42
        elif y == 5
          color = 0x17142E
        elif y == 6
          color = 0x101126
        else
          color = 0x0B0D20
        end

        # Stable orange sun and a pink atmospheric halo.
        var sunDistanceSquared = (x - 21) * (x - 21) + (y - 2.25) * (y - 2.25)
        if sunDistanceSquared < 4.0
          var sunWeight = 1 - sunDistanceSquared / 4.0
          color = self.mix(color, 0xFFB04D, sunWeight)
        elif sunDistanceSquared < 14.44
          var haloWeight = (14.44 - sunDistanceSquared) / 14.44 * 0.42
          color = self.mix(color, 0xFF527D, haloWeight)
        end

        if y >= 5
          # The road darkens toward the viewer and carries a purple center glow.
          var roadWeight = (y - 4) * 0.18
          color = self.mix(color, 0x16102F, roadWeight)
          var centerGlow = 1 - self.absolute(x - 16) / 16.0
          color = self.mix(color, 0x251447, centerGlow * 0.34)

          # Two perspective rails widen toward the viewer from one vanishing
          # point. Their geometry and color are static; only the lane markers
          # below them move.
          var depth = y - 4
          var spread = depth * 3.0
          var leftRail = 16 - spread
          var rightRail = 16 + spread
          var leftDistance = self.absolute(x - leftRail)
          var rightDistance = self.absolute(x - rightRail)
          if leftDistance < 0.7
            color = self.mix(color, 0x28E6F2, 0.82)
          elif rightDistance < 0.7
            color = self.mix(color, 0xF03CB8, 0.82)
          end

          # The only moving elements: discrete lane-marker dashes appear near
          # the vanishing point, then grow across the static road as they
          # approach the camera. Increasing depth widens each marker; phase
          # advances the active marker toward row 7.
          var markerWave = math.sin(phase * 3.0 - depth * 2.7)
          if markerWave > 0.28
            var markerWidth = 1.5 + depth * 3.8
            var markerDistance = self.absolute(x - 16)
            if markerDistance < markerWidth
              var markerStrength = (markerWave - 0.28) / 0.72
              var markerColor = 0x2AD9E8
              if x >= 16 markerColor = 0xE83BAB end
              color = self.mix(color, markerColor, 0.55 + markerStrength * 0.35)
            end
          end
        end
        pixel(x, y, color)
      end
    end
  end
end

return App()
