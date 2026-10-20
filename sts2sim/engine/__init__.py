"""新引擎：在转译的真实游戏代码（sts2sim.gen.game）之上的单机整局驱动。

- manager.SimRunManager：RunManager 的单机移植（建局、生成房间/地图、进房、换幕、胜负）
- combat：战斗驱动（合法动作、出牌、药水、结束回合）
- agents：决策接口与启发式 AI（可被 mod 钩子替换）
- run：整局循环（地图→房间→奖励→下一层）
- gym：强化学习接口（reset/step/observation/action list）
"""
