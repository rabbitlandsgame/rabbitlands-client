// CUSTOM0 is copied from source positions before skinning. Spatial VERTEX
// already contains RD's posed position and cannot define a rest-space cut.
uniform bool smooth_shirt_neckline = false;
varying vec3 neck_rest_position;

bool below_shirt_neckline(vec3 point) {
	if (abs(point.x) < 0.185 && point.z > -0.18 && point.z < 0.12 && point.y > 1.30) {
		float angle = atan(point.x, point.z + 0.030);
		float front = max(cos(angle), 0.0);
		float side = sin(angle);
		float front_squared = front * front;
		float rim = 1.50 + 0.010 * side * side - 0.075 * front_squared * front_squared;
		return point.y < rim - 0.001;
	}
	return false;
}
