import sys
from math import pi, sin, cos
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.DirectGui import DirectSlider, DirectLabel, DirectButton
from panda3d.core import loadPrcFile
from panda3d.core import DirectionalLight, AmbientLight
from panda3d.core import TransparencyAttrib
from panda3d.core import WindowProperties
from panda3d.core import ClockObject
from panda3d.core import CollisionTraverser, CollisionNode
from panda3d.core import CollisionBox, CollisionRay, CollisionHandlerQueue, CollisionHandlerPusher, BitMask32

loadPrcFile('settings.prc')
globalClock = ClockObject.getGlobalClock()

def degToRad(degrees):
    return degrees * (pi / 180.0)

class Minecraft(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)

        # Performance optimizations
        self.render.setAntialias(0)  # Disable antialiasing for better performance
        self.setFrameRateMeter(False)  # Disable built-in frame rate meter
        
        self.heldBlockNode = None

        self.play_music("theme.ogg")

        self.selectedBlockType = 'sand'
        self.fov = 80
        self.mouse_sensitivity = 50
        self.sprinting = False
        self.ctrl_held = False

        self.loadModels()
        self.setupLights()
        self.generateTerrain()

        self.playerNode = self.render.attachNewNode('player')

        self.cTrav_player = CollisionTraverser()
        self.pusher = CollisionHandlerPusher()
        self.ground_queue = CollisionHandlerQueue()

        self.setupCamera()
        self.setupSkybox()
        self.captureMouse()
        self.setupControls()
        self.create_settings_menu()

        self.z_velocity = 0
        self.on_ground = False

        self.taskMgr.add(self.update, 'update')

    def update(self, task):
        dt = globalClock.getDt()

        # Update FPS display
        fps = globalClock.getAverageFrameRate()
        self.fps_text['text'] = f"FPS: {fps:.0f}"

        # ground check from previous frame
        self.on_ground = False
        if self.ground_queue.getNumEntries() > 0:
            self.ground_queue.sortEntries()
            # Check if any ray hit the ground within acceptable distance
            for i in range(self.ground_queue.getNumEntries()):
                ground_hit = self.ground_queue.getEntry(i)
                hit_dist = ground_hit.getSurfacePoint(self.playerNode).getZ()
                if hit_dist > -1.2:  # Slightly more tolerance
                    self.on_ground = True
                    break

        # gravity
        gravity = -20.0
        if not self.on_ground:
            self.z_velocity += gravity * dt
        else:
            # Smooth landing - gradually reduce velocity instead of instant stop
            if self.z_velocity < 0:
                self.z_velocity = max(0, self.z_velocity + gravity * dt * 2)
            else:
                self.z_velocity = 0

        # Verifica se caiu da plataforma
        if self.playerNode.getZ() < -50:
            self.playerNode.setPos(0, 0, 10)  # Volta para a área de nascimento
            self.z_velocity = 0

        # jumping
        if self.keyMap['up'] and self.on_ground:
            if self.keyMap.get('sprint', False) and self.keyMap.get('forward', False):
                self.z_velocity = 16  # pulo mais forte correndo
            else:
                self.z_velocity = 12  # pulo normal

        playerMoveSpeed = 10
        if self.keyMap.get('sprint', False) and self.keyMap.get('forward', False) and not self.keyMap.get('crouch', False):
            playerMoveSpeed = 18
        elif self.keyMap.get('crouch', False):
            playerMoveSpeed = 5  # velocidade reduzida agachado

        x_movement = 0
        y_movement = 0

        player_heading = self.playerNode.getH()

        if self.keyMap['forward']:
            x_movement -= dt * playerMoveSpeed * sin(degToRad(player_heading))
            y_movement += dt * playerMoveSpeed * cos(degToRad(player_heading))
        if self.keyMap['backward']:
            x_movement += dt * playerMoveSpeed * sin(degToRad(player_heading))
            y_movement -= dt * playerMoveSpeed * cos(degToRad(player_heading))
        if self.keyMap['left']:
            x_movement -= dt * playerMoveSpeed * cos(degToRad(player_heading))
            y_movement -= dt * playerMoveSpeed * sin(degToRad(player_heading))
        if self.keyMap['right']:
            x_movement += dt * playerMoveSpeed * cos(degToRad(player_heading))
            y_movement += dt * playerMoveSpeed * sin(degToRad(player_heading))

        # run collisions first
        self.cTrav_player.traverse(self.render)

        # update position
        self.playerNode.setPos(
            self.playerNode.getX() + x_movement,
            self.playerNode.getY() + y_movement,
            self.playerNode.getZ() + self.z_velocity * dt,
            )

        if self.cameraSwingActivated:
            md = self.win.getPointer(0)
            mouseX = md.getX()
            mouseY = md.getY()

            # Obter o centro da janela
            window_center_x = int(self.win.getProperties().getXSize() / 2)
            window_center_y = int(self.win.getProperties().getYSize() / 2)

            mouseChangeX = mouseX - window_center_x
            mouseChangeY = mouseY - window_center_y

            # Aplicar rotação apenas se houve movimento significativo
            if abs(mouseChangeX) > 1 or abs(mouseChangeY) > 1:
                self.playerNode.setH(self.playerNode.getH() - mouseChangeX * dt * self.mouse_sensitivity)
                self.camera.setP(min(90, max(-90, self.camera.getP() - mouseChangeY * dt * self.mouse_sensitivity)))

                # Recentrar o cursor automaticamente
                self.win.movePointer(0, window_center_x, window_center_y)

        return task.cont

    def updateKeyMap(self, key, value):
        self.keyMap[key] = value

    # def updateKeyMap(self, key, value):
    # self.keyMap[key] = value
    # print(f"Tecla: {key}, Valor: {value}, keyMap: {self.keyMap}")

    def SelectedBlockType(self, type):
        self.selectedBlockType = type
        self.updateHeldBlock()

    def captureMouse(self):
        self.cameraSwingActivated = True

        md = self.win.getPointer(0)
        self.lastMouseX = md.getX()
        self.lastMouseY = md.getY()

        props = WindowProperties()
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_relative)
        self.win.requestProperties(props)

    def releaseMouse(self):
        self.cameraSwingActivated = False

        properties = WindowProperties()
        properties.setCursorHidden(False)
        properties.setMouseMode(WindowProperties.M_absolute)
        self.win.requestProperties(properties)

    def leftClick(self):
        self.captureMouse()
        self.removeBlock()

    def loadModels(self):
        self.dirtBlock = self.loader.loadModel('dirt-block.glb')
        self.stoneBlock = self.loader.loadModel('minecraft-stone-block.glb')
        self.sandBlock = self.loader.loadModel('sand-block.glb')

    def removeBlock(self):
        if self.rayQueue.getNumEntries() > 0:
            self.rayQueue.sortEntries()
            rayHit = self.rayQueue.getEntry(0)

            hitNodePath = rayHit.getIntoNodePath()
            hitObject = hitNodePath.getPythonTag('owner')
            distanceFromPlayer = hitObject.getDistance(self.camera)

            if distanceFromPlayer < 12:
                hitNodePath.clearPythonTag('owner')
                hitObject.removeNode()
                self.play_sound("remove_block.ogg")

    def createNewBlock(self, x, y, z, type):
        newBlockNode = self.render.attachNewNode('new-block-placeholder')
        newBlockNode.setPos(x, y, z)

        # Performance optimization: Enable backface culling
        newBlockNode.setRenderModeWireframe()
        newBlockNode.clearRenderMode()
        newBlockNode.setTwoSided(False)

        if type == 'dirt':
            self.dirtBlock.instanceTo(newBlockNode)
            newBlockNode.setScale(1.0)  # Ajuste de escala para igualar aos outros blocos
        elif type == 'sand':
            self.sandBlock.instanceTo(newBlockNode)
        elif type == 'stone':
            self.stoneBlock.instanceTo(newBlockNode)


        blockSolid = CollisionBox((-1, -1, -1), (1, 1, 1))
        blockNode = CollisionNode('block-collision-node')
        blockNode.addSolid(blockSolid)
        blockNode.setFromCollideMask(BitMask32(0x0))
        blockNode.setIntoCollideMask(BitMask32(0x1))
        collider = newBlockNode.attachNewNode(blockNode)
        collider.setPythonTag('owner', newBlockNode)

    def placeBlock(self):
        if self.rayQueue.getNumEntries() > 0:
            self.rayQueue.sortEntries()
            rayHit = self.rayQueue.getEntry(0)
            hitNodePath = rayHit.getIntoNodePath()
            normal = rayHit.getSurfaceNormal(hitNodePath)
            hitObject = hitNodePath.getPythonTag('owner')
            distanceFromPlayer = hitObject.getDistance(self.camera)

            if distanceFromPlayer < 14:
                hitBlockPos = hitObject.getPos()
                newBlockPos = hitBlockPos + normal * 2
                
                # Get player position
                playerPos = self.playerNode.getPos()
                
                # Check if the new block would be placed under the player's feet
                # Player occupies space from feet (playerPos.z - 0.9) to head (playerPos.z + 2)
                playerFeetZ = playerPos.getZ() - 0.9
                playerHeadZ = playerPos.getZ() + 2
                
                # Check if block is too close horizontally and vertically to player
                horizontalDistance = ((newBlockPos.x - playerPos.x) ** 2 + (newBlockPos.y - playerPos.y) ** 2) ** 0.5
                
                # Only prevent placing blocks if:
                # 1. Block would be inside player's body (too close horizontally and within body height)
                # 2. Block would be placed too close under feet (less than 2 units below feet level)
                canPlace = True
                
                # Prevent if block is inside player's body space
                if horizontalDistance < 1.2 and playerFeetZ <= newBlockPos.z <= playerHeadZ:
                    canPlace = False
                
                # Prevent if block is too close under feet (less than 2 units below)
                if horizontalDistance < 1.5 and newBlockPos.z > playerFeetZ - 2 and newBlockPos.z < playerFeetZ:
                    canPlace = False
                
                if canPlace:
                    self.createNewBlock(newBlockPos.x, newBlockPos.y, newBlockPos.z, self.selectedBlockType)
                    self.play_sound("create_block.ogg")

    def setupControls(self):
        self.keyMap = {
            "forward": False,
            "backward": False,
            "left": False,
            "right": False,
            "up": False,
            "sprint": False,
            "crouch": False,
        }

        # self.accept('escape', self.releaseMouse)
        self.accept('mouse1', self.leftClick)
        self.accept('mouse3', self.placeBlock)
        # self.accept('f1', self.captureMouse)  # NOVO: tecla para recapturar o mouse

        self.accept('w', self.updateKeyMap, ['forward', True])
        self.accept('w-up', self.updateKeyMap, ['forward', False])
        self.accept('shift-w', self.updateKeyMap, ['forward', True])
        self.accept('shift-w-up', self.updateKeyMap, ['forward', False])
        self.accept('control-w', self.updateKeyMap, ['forward', True])
        self.accept('control-w-up', self.updateKeyMap, ['forward', False])

        self.accept('a', self.updateKeyMap, ['left', True])
        self.accept('a-up', self.updateKeyMap, ['left', False])
        self.accept('shift-a', self.updateKeyMap, ['left', True])
        self.accept('shift-a-up', self.updateKeyMap, ['left', False])
        self.accept('control-a', self.updateKeyMap, ['left', True])
        self.accept('control-a-up', self.updateKeyMap, ['left', False])

        self.accept('s', self.updateKeyMap, ['backward', True])
        self.accept('s-up', self.updateKeyMap, ['backward', False])
        self.accept('shift-s', self.updateKeyMap, ['backward', True])
        self.accept('shift-s-up', self.updateKeyMap, ['backward', False])
        self.accept('control-s', self.updateKeyMap, ['backward', True])
        self.accept('control-s-up', self.updateKeyMap, ['backward', False])


        self.accept('d', self.updateKeyMap, ['right', True])
        self.accept('d-up', self.updateKeyMap, ['right', False])
        self.accept('shift-d', self.updateKeyMap, ['right', True])
        self.accept('shift-d-up', self.updateKeyMap, ['right', False])
        self.accept('control-d', self.updateKeyMap, ['right', True])
        self.accept('control-d-up', self.updateKeyMap, ['right', False])

        self.accept('space', self.updateKeyMap, ['up', True])
        self.accept('space-up', self.updateKeyMap, ['up', False])
        self.accept('shift-space', self.updateKeyMap, ['jump', True])
        self.accept('shift-space-up', self.updateKeyMap, ['jump', False])
        self.accept('control-space', self.updateKeyMap, ['jump', True])
        self.accept('control-space-up', self.updateKeyMap, ['jump', False])
        self.accept('control-space', self.updateKeyMap, ['up', True])
        self.accept('control-space-up', self.updateKeyMap, ['up', False])
        self.accept('shift-space', self.updateKeyMap, ['up', True])
        self.accept('shift-space-up', self.updateKeyMap, ['up', False])

        self.accept('control', self.updateKeyMap, ['sprint', True])
        self.accept('control-up', self.updateKeyMap, ['sprint', False])

        self.accept('shift', self.updateKeyMap, ['crouch', True])
        self.accept('shift-up', self.updateKeyMap, ['crouch', False])

        self.accept('1', self.SelectedBlockType, ['dirt'])
        self.accept('2', self.SelectedBlockType, ['sand'])
        self.accept('3', self.SelectedBlockType, ['stone'])

        self.accept('escape', self.toggle_settings_menu)

    def setupCamera(self):
        self.disableMouse()
        self.playerNode.setPos(0, 0, 10)
        self.camera.reparentTo(self.playerNode)
        self.camera.setPos(0, -0.9, 1.7)  # Head height position (eye level)
        self.camLens.setFov(self.fov)

        crosshairs = OnscreenImage(
            image = 'crosshairs.png',
            pos = (0, 0, 0),
            scale = 0.05,
        )
        crosshairs.setTransparency(TransparencyAttrib.MAlpha)

        # FPS display
        self.fps_text = DirectLabel(
            text="FPS: 0",
            pos=(-1.3, 0, 0.9),
            scale=0.06,
            text_fg=(1, 1, 1, 1),
            frameColor=(0, 0, 0, 0)
        )

        self.cTrav = CollisionTraverser()
        ray = CollisionRay()
        ray.setFromLens(self.camNode, (0, 0))
        rayNode = CollisionNode('line-of-sight')
        rayNode.addSolid(ray)
        rayNode.setFromCollideMask(BitMask32(0x1))
        rayNode.setIntoCollideMask(BitMask32(0x0))
        rayNodePath = self.camera.attachNewNode(rayNode)
        self.rayQueue = CollisionHandlerQueue()
        self.cTrav.addCollider(rayNodePath, self.rayQueue)

        # Player collision setup
        player_cnode = CollisionNode('player')
        player_cnode.addSolid(CollisionBox((-0.6, -0.6, -0.9), (0.6, 0.6, 2)))
        player_cnode.setFromCollideMask(BitMask32(0x1))
        player_cnode.setIntoCollideMask(BitMask32(0x0))
        player_collider = self.playerNode.attachNewNode(player_cnode)
        self.pusher.addCollider(player_collider, self.playerNode)
        self.cTrav_player.addCollider(player_collider, self.pusher)

        # Ground check rays - multiple rays for better edge detection
        ground_cnode = CollisionNode('ground_ray_cnode')
        
        # Center ray
        center_ray = CollisionRay()
        center_ray.setOrigin(0, 0, -0.9)
        center_ray.setDirection(0, 0, -1)
        ground_cnode.addSolid(center_ray)
        
        # Corner rays for edge detection
        corner_offset = 0.5
        for x_offset in [-corner_offset, corner_offset]:
            for y_offset in [-corner_offset, corner_offset]:
                corner_ray = CollisionRay()
                corner_ray.setOrigin(x_offset, y_offset, -0.9)
                corner_ray.setDirection(0, 0, -1)
                ground_cnode.addSolid(corner_ray)
        
        ground_cnode.setFromCollideMask(BitMask32(0x1))
        ground_cnode.setIntoCollideMask(BitMask32(0x0))
        ground_collider = self.playerNode.attachNewNode(ground_cnode)
        self.cTrav_player.addCollider(ground_collider, self.ground_queue)

    def create_settings_menu(self):
        self.settings_menu = self.aspect2d.attachNewNode("settings_menu")
        self.settings_menu.hide()

        # FOV
        self.fov_label = DirectLabel(
            parent=self.settings_menu,
            text="FOV",
            pos=(-0.837, 0, 0.4),
            scale=0.07
        )
        self.fov_slider = DirectSlider(
            parent=self.settings_menu,
            range=(60, 120),
            value=self.fov,
            pageSize=5,
            command=self.set_fov,
            pos=(0.1, 0, 0.35)
        )

        # Sensibilidade do mouse
        self.sensitivity_label = DirectLabel(
            parent=self.settings_menu,
            text="Sensibilidade do Mouse",
            pos=(-0.53, 0, 0.15),
            scale=0.07
        )
        self.sensitivity_slider = DirectSlider(
            parent=self.settings_menu,
            range=(10, 100),
            value=self.mouse_sensitivity,
            pageSize=5,
            command=self.set_mouse_sensitivity,
            pos=(0.1, 0, 0.1)
        )

        # FPS
        self.fps_label = DirectLabel(
            parent=self.settings_menu,
            text="FPS",
            pos=(-0.84, 0, -0.09),
            scale=0.07
        )
        self.fps_slider = DirectSlider(
            parent=self.settings_menu,
            range=(30, 240),
            value=60,
            pageSize=5,
            command=self.set_fps,
            pos=(0.1, 0, -0.15)
        )

        # Botões
        self.resume_button = DirectButton(
            parent=self.settings_menu,
            text="Continuar",
            command=self.toggle_settings_menu,
            pos=(0, 0, -0.25),
            scale=0.07
        )
        self.quit_button = DirectButton(
            parent=self.settings_menu,
            text="Sair",
            command=self.quit_game,
            pos=(0, 0, -0.35),
            scale=0.07
        )

    def set_fov(self):
        self.fov = self.fov_slider['value']
        self.camLens.setFov(self.fov)
        self.updateHeldBlockPosition()

    def set_mouse_sensitivity(self):
        self.mouse_sensitivity = self.sensitivity_slider['value']

    def set_fps(self):
        fps = self.fps_slider['value']
        ClockObject.getGlobalClock().setMode(ClockObject.MLimited)
        ClockObject.getGlobalClock().setFrameRate(fps)

    def toggle_settings_menu(self):
        window_center_x = int(self.win.getProperties().getXSize() / 2)
        window_center_y = int(self.win.getProperties().getYSize() / 2)
        self.win.movePointer(0, window_center_x, window_center_y)
        if self.settings_menu.isHidden():
            self.settings_menu.show()
            self.releaseMouse()
        else:
            self.settings_menu.hide()
            self.captureMouse()

    def quit_game(self):
        sys.exit()

    def setupSkybox(self):
        skybox = self.loader.loadModel('skybox/skybox.egg')
        skybox.setScale(500)
        skybox.setBin('background', 1)
        skybox.setDepthWrite(0)
        skybox.setLightOff()
        skybox.reparentTo(self.render)

    def generateTerrain(self):
        # Generate optimized 25x25x25 terrain with proper layering
        # Only generate surface and near-surface blocks for better performance
        for z in range(8):  # Reduced depth for better performance
            for y in range(25):
                for x in range(25):
                    # Calculate block type based on depth
                    if z == 0:
                        block_type = 'sand'   # Top layer is sand
                    elif z <= 3:
                        block_type = 'dirt'   # Next 3 layers are dirt
                    else:
                        block_type = 'stone'  # Everything below is stone
                    
                    self.createNewBlock(
                        x * 2 - 25,  # Center the terrain
                        y * 2 - 25,  # Center the terrain
                        -z * 2,      # Build downward
                        block_type
                    )

    def setupLights(self):
        mainLight = DirectionalLight('main light')
        mainLightNodePath = self.render.attachNewNode(mainLight)
        mainLightNodePath.setHpr(30, -60, 0)
        self.render.setLight(mainLightNodePath)

        ambientLight = AmbientLight('ambient light')
        ambientLight.setColor((0.3, 0.3, 0.3, 1))
        ambientLightNodePath = self.render.attachNewNode(ambientLight)
        self.render.setLight(ambientLightNodePath)

    def play_music(self, file_name, loop=True, volume=0.3):
        self.music = self.loader.loadMusic(file_name)
        self.music.setLoop(loop)
        self.music.setVolume(volume)
        self.music.play()

    def play_sound(self, file_name, volume=1.0):
        sound = self.loader.loadSfx(file_name)
        sound.setVolume(volume)
        sound.play()

    def updateHeldBlock(self):
        if self.heldBlockNode:
            self.heldBlockNode.removeNode()
            self.heldBlockNode = None
        if self.selectedBlockType:
            self.heldBlockNode = self.render.attachNewNode('held-block')
            if self.selectedBlockType == 'dirt':
                self.dirtBlock.instanceTo(self.heldBlockNode)
            elif self.selectedBlockType == 'sand':
                self.sandBlock.instanceTo(self.heldBlockNode)
            elif self.selectedBlockType == 'stone':
                self.stoneBlock.instanceTo(self.heldBlockNode)


            # Ajuste a posição para "ficar na mão" do jogador
            self.heldBlockNode.reparentTo(self.camera)
            self.updateHeldBlockPosition()

    def updateHeldBlockPosition(self):
        if self.heldBlockNode:
            # Calcular posição baseada no FOV
            # FOV menor = bloco mais próximo, FOV maior = bloco mais longe
            fov_factor = self.fov / 80.0  # 80 é o FOV base

            # Ajustar posição Y (profundidade) baseada no FOV
            base_y = 1.5
            adjusted_y = base_y * fov_factor

            # Ajustar posição Z (altura) ligeiramente baseada no FOV
            base_z = -0.7
            adjusted_z = base_z * (1.0 + (fov_factor - 1.0) * 0.3)

            self.heldBlockNode.setPos(0.7, adjusted_y, adjusted_z)
            self.heldBlockNode.setScale(0.3)

game = Minecraft()
game.run()
