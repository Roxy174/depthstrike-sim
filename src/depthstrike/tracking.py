"""Time-aware filtering that never keeps invalid interaction points alive."""
import math
from collections import Counter
from dataclasses import replace

import numpy as np

from .config import AppConfig
from .types import Joint3D, SkeletonFrame


class SkeletonTracker:
    def __init__(self, config: AppConfig):
        self.config = config
        self._quality_frames = 0
        self._hand_quality = {h: Counter() for h in ('left', 'right')}
        self.reset()

    def quality_summary(self):
        return {'frames': self._quality_frames, 'scope': 'filtered_wrist_availability_not_accuracy',
                'hands': {h: dict(c) for h, c in self._hand_quality.items()}}

    def _observe_quality(self, frame):
        self._quality_frames += 1
        for hand, counts in self._hand_quality.items():
            joint = frame.joints.get(f'{hand}_wrist')
            reason = ('measured_3d' if joint is not None and joint.is_observed else
                      (joint.invalid_reason or 'missing_joint') if joint is not None else 'missing_joint')
            counts[reason] += 1
        return frame

    def reset(self):
        self._previous = None
        self._velocities = {}
        self._kalman = {}
        self._display_history = {}
        self._raw_history = {}
        self.display_joints = {}

    def update(self, frame: SkeletonFrame) -> SkeletonFrame:
        previous = self._previous
        dt = frame.timestamp_s-previous.timestamp_s if previous else None
        if dt is not None and dt <= 0:
            self.reset()
            return self._observe_quality(SkeletonFrame(frame.frame_id, frame.timestamp_s,
                                 {name: Joint3D(None, invalid_reason="timestamp_invalid") for name in frame.joints}))
        connected = dt is not None and dt <= self.config.max_track_gap_s
        if not connected:
            self._velocities = {}
            self._kalman = {}
            self._display_history = {}
            self._raw_history = {}
        alpha = 1-math.exp(-dt/self.config.smoothing_tau_s) if connected and self.config.smoothing_tau_s else 1.
        joints = {}
        names = dict.fromkeys((*frame.joints, *self._kalman, *self._display_history, *self._raw_history))
        for name in names:
            joint = frame.joints.get(name, Joint3D(None, invalid_reason="missing_joint"))
            anchor = self._raw_history.get(name)
            if anchor is not None and frame.timestamp_s-anchor[0] > self.config.max_track_gap_s:
                self._raw_history.pop(name, None)
                anchor = None
            if not joint.is_observed or joint.confidence < self.config.confidence_threshold:
                self._kalman.pop(name, None)
                joints[name] = Joint3D(None, invalid_reason=joint.invalid_reason or
                                       ("low_confidence" if joint.position is not None else "missing_joint"))
                continue
            if self.config.reject_tracking_outliers:
                if anchor is not None:
                    body = name == "nose" or name.endswith(("_shoulder", "_hip"))
                    speed_limit = self.config.tracking_body_speed_m_s if body else self.config.tracking_hand_speed_m_s
                    allowance = self.config.tracking_outlier_slack_m + speed_limit*(frame.timestamp_s-anchor[0])
                    if np.linalg.norm(joint.position-anchor[1]) > allowance:
                        # Do not teach a filter or the next gate a rejected jump.
                        self._kalman.pop(name, None)
                        self._velocities.pop(name, None)
                        joints[name] = Joint3D(None, invalid_reason="motion_outlier")
                        continue
                self._raw_history[name] = (frame.timestamp_s, joint.position.copy())
            old = previous.joints.get(name) if connected else None
            position = joint.position
            if self.config.filter_mode == "kalman":
                position = self._kalman_update(name, joint, dt if connected else None)
            elif old is not None and old.position is not None:
                weight = alpha
                if self.config.filter_mode == "one_euro":
                    raw_velocity = (position-old.position)/dt
                    derivative_weight = 1/(1+1/(2*math.pi*dt))
                    velocity = self._velocities.get(name, np.zeros(3))
                    velocity = velocity+derivative_weight*(raw_velocity-velocity)
                    self._velocities[name] = velocity
                    cutoff = self.config.one_euro_min_cutoff+self.config.one_euro_beta*np.linalg.norm(velocity)
                    weight = 1/(1+1/(2*math.pi*cutoff*dt))
                position = old.position + weight*(position-old.position)
            else:
                self._velocities.pop(name, None)
            joints[name] = replace(joint, position=position)
        result = SkeletonFrame(frame.frame_id, frame.timestamp_s, joints)
        self.display_joints = {}
        if self.config.partial_tracking:
            for name, joint in joints.items():
                history = self._display_history.get(name)
                if joint.is_observed:
                    velocity = np.zeros(3)
                    if history is not None and previous is not None and previous.joints.get(name, Joint3D(None)).is_observed:
                        velocity = (joint.position-history[1].position)/(frame.timestamp_s-history[0])
                        speed_limit = min(5., self.config.tracking_body_speed_m_s) if name == "nose" or name.endswith(("_shoulder", "_hip")) else 5.
                        velocity *= min(1., speed_limit/max(1e-9, np.linalg.norm(velocity)))
                    self._display_history[name] = (frame.timestamp_s, joint, velocity)
                elif history is not None:
                    age = frame.timestamp_s-history[0]
                    if 0 < age <= self.config.prediction_horizon_s:
                        ratio = 1-age/self.config.prediction_horizon_s
                        self.display_joints[name] = Joint3D(history[1].position+age*history[2],
                            history[1].confidence*ratio, provenance="predicted",
                            depth_quality=history[1].depth_quality*ratio, age_s=age)
                    else:
                        self._display_history.pop(name, None)
        self._previous = result
        return self._observe_quality(result)

    def _kalman_update(self, name, joint, dt):
        prior = self._kalman.get(name)
        if prior is None or dt is None:
            state = np.concatenate((joint.position, np.zeros(3)))
            covariance = np.diag((.01, .01, .01, 1., 1., 1.))
        else:
            state, covariance = prior
            transition = np.eye(6)
            transition[:3, 3:] = np.eye(3)*dt
            acceleration = np.vstack((np.eye(3)*dt*dt/2, np.eye(3)*dt))
            state = transition@state
            covariance = transition@covariance@transition.T+4.*acceleration@acceleration.T
            # Quality is an engineering weight, not a calibrated probability.
            sigma = .015/max(.05, joint.confidence*joint.depth_quality)
            residual_covariance = covariance[:3, :3]+np.eye(3)*sigma*sigma
            gain = np.linalg.solve(residual_covariance, covariance[:3, :]).T
            state = state+gain@(joint.position-state[:3])
            residual = np.eye(6)
            residual[:, :3] -= gain
            covariance = residual@covariance@residual.T+gain@(np.eye(3)*sigma*sigma)@gain.T
        self._kalman[name] = state, covariance
        return state[:3]
