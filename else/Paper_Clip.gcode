; HEADER_BLOCK_START
; BambuStudio 01.10.01.50
; model printing time: 44s; total estimated time: 7m 15s
; total layer number: 5
; total filament length [mm] : 81.61
; total filament volume [cm^3] : 196.30
; total filament weight [g] : 0.25
; filament_density: 1.24,1.26,1.24
; filament_diameter: 1.75,1.75,1.75
; max_z_height: 1.00
; HEADER_BLOCK_END

; CONFIG_BLOCK_START
; accel_to_decel_enable = 0
; accel_to_decel_factor = 50%
; activate_air_filtration = 0,0,0
; additional_cooling_fan_speed = 70,70,70
; auxiliary_fan = 1
; bed_custom_model = 
; bed_custom_texture = 
; bed_exclude_area = 0x0,18x0,18x28,0x28
; before_layer_change_gcode = 
; best_object_pos = 0.5,0.5
; bottom_shell_layers = 3
; bottom_shell_thickness = 0
; bottom_surface_pattern = monotonic
; bridge_angle = 0
; bridge_flow = 1
; bridge_no_support = 0
; bridge_speed = 50
; brim_object_gap = 0.1
; brim_type = auto_brim
; brim_width = 5
; chamber_temperatures = 0,0,0
; change_filament_gcode = M620 S[next_extruder]A\nM204 S9000\n{if toolchange_count > 1 && (z_hop_types[current_extruder] == 0 || z_hop_types[current_extruder] == 3)}\nG17\nG2 Z{z_after_toolchange + 0.4} I0.86 J0.86 P1 F10000 ; spiral lift a little from second lift\n{endif}\nG1 Z{max_layer_z + 3.0} F1200\n\nG1 X70 F21000\nG1 Y245\nG1 Y265 F3000\nM400\nM106 P1 S0\nM106 P2 S0\n{if old_filament_temp > 142 && next_extruder < 255}\nM104 S[old_filament_temp]\n{endif}\n{if long_retractions_when_cut[previous_extruder]}\nM620.11 S1 I[previous_extruder] E-{retraction_distances_when_cut[previous_extruder]} F{old_filament_e_feedrate}\n{else}\nM620.11 S0\n{endif}\nM400\nG1 X90 F3000\nG1 Y255 F4000\nG1 X100 F5000\nG1 X120 F15000\nG1 X20 Y50 F21000\nG1 Y-3\n{if toolchange_count == 2}\n; get travel path for change filament\nM620.1 X[travel_point_1_x] Y[travel_point_1_y] F21000 P0\nM620.1 X[travel_point_2_x] Y[travel_point_2_y] F21000 P1\nM620.1 X[travel_point_3_x] Y[travel_point_3_y] F21000 P2\n{endif}\nM620.1 E F[old_filament_e_feedrate] T{nozzle_temperature_range_high[previous_extruder]}\nT[next_extruder]\nM620.1 E F[new_filament_e_feedrate] T{nozzle_temperature_range_high[next_extruder]}\n\n{if next_extruder < 255}\n{if long_retractions_when_cut[previous_extruder]}\nM620.11 S1 I[previous_extruder] E{retraction_distances_when_cut[previous_extruder]} F{old_filament_e_feedrate}\nM628 S1\nG92 E0\nG1 E{retraction_distances_when_cut[previous_extruder]} F[old_filament_e_feedrate]\nM400\nM629 S1\n{else}\nM620.11 S0\n{endif}\nG92 E0\n{if flush_length_1 > 1}\nM83\n; FLUSH_START\n; always use highest temperature to flush\nM400\n{if filament_type[next_extruder] == "PETG"}\nM109 S260\n{elsif filament_type[next_extruder] == "PVA"}\nM109 S210\n{else}\nM109 S[nozzle_temperature_range_high]\n{endif}\n{if flush_length_1 > 23.7}\nG1 E23.7 F{old_filament_e_feedrate} ; do not need pulsatile flushing for start part\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\nG1 E{(flush_length_1 - 23.7) * 0.23} F{old_filament_e_feedrate}\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\nG1 E{(flush_length_1 - 23.7) * 0.23} F{new_filament_e_feedrate}\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\nG1 E{(flush_length_1 - 23.7) * 0.23} F{new_filament_e_feedrate}\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\nG1 E{(flush_length_1 - 23.7) * 0.23} F{new_filament_e_feedrate}\n{else}\nG1 E{flush_length_1} F{old_filament_e_feedrate}\n{endif}\n; FLUSH_END\nG1 E-[old_retract_length_toolchange] F1800\nG1 E[old_retract_length_toolchange] F300\n{endif}\n\n{if flush_length_2 > 1}\n\nG91\nG1 X3 F12000; move aside to extrude\nG90\nM83\n\n; FLUSH_START\nG1 E{flush_length_2 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_2 * 0.02} F50\nG1 E{flush_length_2 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_2 * 0.02} F50\nG1 E{flush_length_2 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_2 * 0.02} F50\nG1 E{flush_length_2 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_2 * 0.02} F50\nG1 E{flush_length_2 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_2 * 0.02} F50\n; FLUSH_END\nG1 E-[new_retract_length_toolchange] F1800\nG1 E[new_retract_length_toolchange] F300\n{endif}\n\n{if flush_length_3 > 1}\n\nG91\nG1 X3 F12000; move aside to extrude\nG90\nM83\n\n; FLUSH_START\nG1 E{flush_length_3 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_3 * 0.02} F50\nG1 E{flush_length_3 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_3 * 0.02} F50\nG1 E{flush_length_3 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_3 * 0.02} F50\nG1 E{flush_length_3 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_3 * 0.02} F50\nG1 E{flush_length_3 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_3 * 0.02} F50\n; FLUSH_END\nG1 E-[new_retract_length_toolchange] F1800\nG1 E[new_retract_length_toolchange] F300\n{endif}\n\n{if flush_length_4 > 1}\n\nG91\nG1 X3 F12000; move aside to extrude\nG90\nM83\n\n; FLUSH_START\nG1 E{flush_length_4 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_4 * 0.02} F50\nG1 E{flush_length_4 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_4 * 0.02} F50\nG1 E{flush_length_4 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_4 * 0.02} F50\nG1 E{flush_length_4 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_4 * 0.02} F50\nG1 E{flush_length_4 * 0.18} F{new_filament_e_feedrate}\nG1 E{flush_length_4 * 0.02} F50\n; FLUSH_END\n{endif}\n; FLUSH_START\nM400\nM109 S[new_filament_temp]\nG1 E2 F{new_filament_e_feedrate} ;Compensate for filament spillage during waiting temperature\n; FLUSH_END\nM400\nG92 E0\nG1 E-[new_retract_length_toolchange] F1800\nM106 P1 S255\nM400 S3\n\nG1 X70 F5000\nG1 X90 F3000\nG1 Y255 F4000\nG1 X105 F5000\nG1 Y265 F5000\nG1 X70 F10000\nG1 X100 F5000\nG1 X70 F10000\nG1 X100 F5000\n\nG1 X70 F10000\nG1 X80 F15000\nG1 X60\nG1 X80\nG1 X60\nG1 X80 ; shake to put down garbage\nG1 X100 F5000\nG1 X165 F15000; wipe and shake\nG1 Y256 ; move Y to aside, prevent collision\nM400\nG1 Z{max_layer_z + 3.0} F3000\n{if layer_z <= (initial_layer_print_height + 0.001)}\nM204 S[initial_layer_acceleration]\n{else}\nM204 S[default_acceleration]\n{endif}\n{else}\nG1 X[x_after_toolchange] Y[y_after_toolchange] Z[z_after_toolchange] F12000\n{endif}\nM621 S[next_extruder]A\n
; close_fan_the_first_x_layers = 1,1,1
; complete_print_exhaust_fan_speed = 70,70,70
; cool_plate_temp = 35,35,35
; cool_plate_temp_initial_layer = 35,35,35
; curr_bed_type = Textured PEI Plate
; default_acceleration = 10000
; default_filament_colour = ;;
; default_filament_profile = "Bambu PLA Basic @BBL X1C"
; default_jerk = 0
; default_print_profile = 0.20mm Standard @BBL X1C
; deretraction_speed = 30
; detect_narrow_internal_solid_infill = 1
; detect_overhang_wall = 1
; detect_thin_wall = 0
; draft_shield = disabled
; during_print_exhaust_fan_speed = 70,70,70
; elefant_foot_compensation = 0.15
; enable_arc_fitting = 1
; enable_long_retraction_when_cut = 2
; enable_overhang_bridge_fan = 1,1,1
; enable_overhang_speed = 1
; enable_pressure_advance = 0,0,0
; enable_prime_tower = 0
; enable_support = 0
; enforce_support_layers = 0
; eng_plate_temp = 0,0,0
; eng_plate_temp_initial_layer = 0,0,0
; ensure_vertical_shell_thickness = 1
; exclude_object = 1
; extruder_clearance_dist_to_rod = 33
; extruder_clearance_height_to_lid = 90
; extruder_clearance_height_to_rod = 34
; extruder_clearance_max_radius = 68
; extruder_colour = #018001
; extruder_offset = 0x2
; extruder_type = DirectDrive
; fan_cooling_layer_time = 100,100,100
; fan_max_speed = 100,100,100
; fan_min_speed = 100,100,100
; filament_colour = #161616;#FF6A13;#FFFFFF
; filament_cost = 20,24.99,20
; filament_density = 1.24,1.26,1.24
; filament_diameter = 1.75,1.75,1.75
; filament_end_gcode = "; filament end gcode \nM106 P3 S0\n";"; filament end gcode \nM106 P3 S0\n";"; filament end gcode \nM106 P3 S0\n"
; filament_flow_ratio = 0.98,0.98,0.98
; filament_ids = GFL99;GFA00;GFL99
; filament_is_support = 0,0,0
; filament_long_retractions_when_cut = nil,1,nil
; filament_max_volumetric_speed = 12,21,12
; filament_minimal_purge_on_wipe_tower = 15,15,15
; filament_notes = 
; filament_retraction_distances_when_cut = nil,18,nil
; filament_scarf_gap = 15%,0%,15%
; filament_scarf_height = 10%,10%,10%
; filament_scarf_length = 10,10,10
; filament_scarf_seam_type = none,none,none
; filament_settings_id = "Generic PLA";"Bambu PLA Basic @BBL X1C";"Generic PLA"
; filament_shrink = 100%,100%,100%
; filament_soluble = 0,0,0
; filament_start_gcode = "; filament start gcode\n{if  (bed_temperature[current_extruder] >55)||(bed_temperature_initial_layer[current_extruder] >55)}M106 P3 S200\n{elsif(bed_temperature[current_extruder] >50)||(bed_temperature_initial_layer[current_extruder] >50)}M106 P3 S150\n{elsif(bed_temperature[current_extruder] >45)||(bed_temperature_initial_layer[current_extruder] >45)}M106 P3 S50\n{endif}\n\n{if activate_air_filtration[current_extruder] && support_air_filtration}\nM106 P3 S{during_print_exhaust_fan_speed_num[current_extruder]} \n{endif}";"; filament start gcode\n{if  (bed_temperature[current_extruder] >55)||(bed_temperature_initial_layer[current_extruder] >55)}M106 P3 S200\n{elsif(bed_temperature[current_extruder] >50)||(bed_temperature_initial_layer[current_extruder] >50)}M106 P3 S150\n{elsif(bed_temperature[current_extruder] >45)||(bed_temperature_initial_layer[current_extruder] >45)}M106 P3 S50\n{endif}\nM142 P1 R35 S40\n{if activate_air_filtration[current_extruder] && support_air_filtration}\nM106 P3 S{during_print_exhaust_fan_speed_num[current_extruder]} \n{endif}";"; filament start gcode\n{if  (bed_temperature[current_extruder] >55)||(bed_temperature_initial_layer[current_extruder] >55)}M106 P3 S200\n{elsif(bed_temperature[current_extruder] >50)||(bed_temperature_initial_layer[current_extruder] >50)}M106 P3 S150\n{elsif(bed_temperature[current_extruder] >45)||(bed_temperature_initial_layer[current_extruder] >45)}M106 P3 S50\n{endif}\n\n{if activate_air_filtration[current_extruder] && support_air_filtration}\nM106 P3 S{during_print_exhaust_fan_speed_num[current_extruder]} \n{endif}"
; filament_type = PLA;PLA;PLA
; filament_vendor = Generic;"Bambu Lab";Generic
; filename_format = {input_filename_base}_{filament_type[0]}_{print_time}.gcode
; filter_out_gap_fill = 0
; first_layer_print_sequence = 0
; flush_into_infill = 0
; flush_into_objects = 0
; flush_into_support = 1
; flush_multiplier = 1
; flush_volumes_matrix = 0,579,632,175,0,526,180,339,0
; flush_volumes_vector = 140,140,140,140,140,140
; full_fan_speed_layer = 0,0,0
; fuzzy_skin = none
; fuzzy_skin_point_distance = 0.8
; fuzzy_skin_thickness = 0.3
; gap_infill_speed = 250
; gcode_add_line_number = 0
; gcode_flavor = marlin
; has_scarf_joint_seam = 0
; head_wrap_detect_zone = 
; host_type = octoprint
; hot_plate_temp = 55,55,55
; hot_plate_temp_initial_layer = 55,55,55
; independent_support_layer_height = 1
; infill_combination = 0
; infill_direction = 45
; infill_jerk = 9
; infill_wall_overlap = 15%
; initial_layer_acceleration = 500
; initial_layer_flow_ratio = 1
; initial_layer_infill_speed = 105
; initial_layer_jerk = 9
; initial_layer_line_width = 0.5
; initial_layer_print_height = 0.2
; initial_layer_speed = 50
; inner_wall_acceleration = 0
; inner_wall_jerk = 9
; inner_wall_line_width = 0.45
; inner_wall_speed = 300
; interface_shells = 0
; internal_bridge_support_thickness = 0.8
; internal_solid_infill_line_width = 0.42
; internal_solid_infill_pattern = zig-zag
; internal_solid_infill_speed = 250
; ironing_direction = 45
; ironing_flow = 10%
; ironing_inset = 0.21
; ironing_pattern = zig-zag
; ironing_spacing = 0.15
; ironing_speed = 30
; ironing_type = no ironing
; is_infill_first = 0
; layer_change_gcode = ; layer num/total_layer_count: {layer_num+1}/[total_layer_count]\nM622.1 S1 ; for prev firware, default turned on\nM1002 judge_flag timelapse_record_flag\nM622 J1\n{if timelapse_type == 0} ; timelapse without wipe tower\nM971 S11 C10 O0\nM1004 S5 P1  ; external shutter\n{elsif timelapse_type == 1} ; timelapse with wipe tower\nG92 E0\nG1 E-[retraction_length] F1800\nG17\nG2 Z{layer_z + 0.4} I0.86 J0.86 P1 F20000 ; spiral lift a little\nG1 X65 Y245 F20000 ; move to safe pos\nG17\nG2 Z{layer_z} I0.86 J0.86 P1 F20000\nG1 Y265 F3000\nM400\nM1004 S5 P1  ; external shutter\nM400 P300\nM971 S11 C11 O0\nG92 E0\nG1 E[retraction_length] F300\nG1 X100 F5000\nG1 Y255 F20000\n{endif}\nM623\n; update layer progress\nM73 L{layer_num+1}\nM991 S0 P{layer_num} ;notify layer change
; layer_height = 0.2
; line_width = 0.42
; long_retractions_when_cut = 0
; machine_end_gcode = ;===== date: 20230428 =====================\nM400 ; wait for buffer to clear\nG92 E0 ; zero the extruder\nG1 E-0.8 F1800 ; retract\nG1 Z{max_layer_z + 0.5} F900 ; lower z a little\nG1 X65 Y245 F12000 ; move to safe pos \nG1 Y265 F3000\n\nG1 X65 Y245 F12000\nG1 Y265 F3000\nM140 S0 ; turn off bed\nM106 S0 ; turn off fan\nM106 P2 S0 ; turn off remote part cooling fan\nM106 P3 S0 ; turn off chamber cooling fan\n\nG1 X100 F12000 ; wipe\n; pull back filament to AMS\nM620 S255\nG1 X20 Y50 F12000\nG1 Y-3\nT255\nG1 X65 F12000\nG1 Y265\nG1 X100 F12000 ; wipe\nM621 S255\nM104 S0 ; turn off hotend\n\nM622.1 S1 ; for prev firware, default turned on\nM1002 judge_flag timelapse_record_flag\nM622 J1\n    M400 ; wait all motion done\n    M991 S0 P-1 ;end smooth timelapse at safe pos\n    M400 S3 ;wait for last picture to be taken\nM623; end of "timelapse_record_flag"\n\nM400 ; wait all motion done\nM17 S\nM17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom\n{if (max_layer_z + 100.0) < 250}\n    G1 Z{max_layer_z + 100.0} F600\n    G1 Z{max_layer_z +98.0}\n{else}\n    G1 Z250 F600\n    G1 Z248\n{endif}\nM400 P100\nM17 R ; restore z current\n\nM220 S100  ; Reset feedrate magnitude\nM201.2 K1.0 ; Reset acc magnitude\nM73.2   R1.0 ;Reset left time magnitude\nM1002 set_gcode_claim_speed_level : 0\n\nM17 X0.8 Y0.8 Z0.5 ; lower motor current to 45% power\n
; machine_load_filament_time = 29
; machine_max_acceleration_e = 5000,5000
; machine_max_acceleration_extruding = 20000,20000
; machine_max_acceleration_retracting = 5000,5000
; machine_max_acceleration_travel = 9000,9000
; machine_max_acceleration_x = 20000,20000
; machine_max_acceleration_y = 20000,20000
; machine_max_acceleration_z = 500,200
; machine_max_jerk_e = 2.5,2.5
; machine_max_jerk_x = 9,9
; machine_max_jerk_y = 9,9
; machine_max_jerk_z = 3,3
; machine_max_speed_e = 30,30
; machine_max_speed_x = 500,200
; machine_max_speed_y = 500,200
; machine_max_speed_z = 20,20
; machine_min_extruding_rate = 0,0
; machine_min_travel_rate = 0,0
; machine_pause_gcode = M400 U1
; machine_start_gcode = ;===== machine: P1S ========================\n;===== date: 20231107 =====================\n;===== turn on the HB fan & MC board fan =================\nM104 S75 ;set extruder temp to turn on the HB fan and prevent filament oozing from nozzle\nM710 A1 S255 ;turn on MC fan by default(P1S)\n;===== reset machine status =================\nM290 X40 Y40 Z2.6666666\nG91\nM17 Z0.4 ; lower the z-motor current\nG380 S2 Z30 F300 ; G380 is same as G38; lower the hotbed , to prevent the nozzle is below the hotbed\nG380 S2 Z-25 F300 ;\nG1 Z5 F300;\nG90\nM17 X1.2 Y1.2 Z0.75 ; reset motor current to default\nM960 S5 P1 ; turn on logo lamp\nG90\nM220 S100 ;Reset Feedrate\nM221 S100 ;Reset Flowrate\nM73.2   R1.0 ;Reset left time magnitude\nM1002 set_gcode_claim_speed_level : 5\nM221 X0 Y0 Z0 ; turn off soft endstop to prevent protential logic problem\nG29.1 Z{+0.0} ; clear z-trim value first\nM204 S10000 ; init ACC set to 10m/s^2\n\n;===== heatbed preheat ====================\nM1002 gcode_claim_action : 2\nM140 S[bed_temperature_initial_layer_single] ;set bed temp\nM190 S[bed_temperature_initial_layer_single] ;wait for bed temp\n\n\n\n;=============turn on fans to prevent PLA jamming=================\n{if filament_type[initial_extruder]=="PLA"}\n    {if (bed_temperature[initial_extruder] >45)||(bed_temperature_initial_layer[initial_extruder] >45)}\n    M106 P3 S180\n    {endif};Prevent PLA from jamming\n{endif}\nM106 P2 S100 ; turn on big fan ,to cool down toolhead\n\n;===== prepare print temperature and material ==========\nM104 S[nozzle_temperature_initial_layer] ;set extruder temp\nG91\nG0 Z10 F1200\nG90\nG28 X\nM975 S1 ; turn on\nG1 X60 F12000\nG1 Y245\nG1 Y265 F3000\nM620 M\nM620 S[initial_extruder]A   ; switch material if AMS exist\n    M109 S[nozzle_temperature_initial_layer]\n    G1 X120 F12000\n\n    G1 X20 Y50 F12000\n    G1 Y-3\n    T[initial_extruder]\n    G1 X54 F12000\n    G1 Y265\n    M400\nM621 S[initial_extruder]A\nM620.1 E F{filament_max_volumetric_speed[initial_extruder]/2.4053*60} T{nozzle_temperature_range_high[initial_extruder]}\n\n\nM412 S1 ; ===turn on filament runout detection===\n\nM109 S250 ;set nozzle to common flush temp\nM106 P1 S0\nG92 E0\nG1 E50 F200\nM400\nM104 S[nozzle_temperature_initial_layer]\nG92 E0\nG1 E50 F200\nM400\nM106 P1 S255\nG92 E0\nG1 E5 F300\nM109 S{nozzle_temperature_initial_layer[initial_extruder]-20} ; drop nozzle temp, make filament shink a bit\nG92 E0\nG1 E-0.5 F300\n\nG1 X70 F9000\nG1 X76 F15000\nG1 X65 F15000\nG1 X76 F15000\nG1 X65 F15000; shake to put down garbage\nG1 X80 F6000\nG1 X95 F15000\nG1 X80 F15000\nG1 X165 F15000; wipe and shake\nM400\nM106 P1 S0\n;===== prepare print temperature and material end =====\n\n\n;===== wipe nozzle ===============================\nM1002 gcode_claim_action : 14\nM975 S1\nM106 S255\nG1 X65 Y230 F18000\nG1 Y264 F6000\nM109 S{nozzle_temperature_initial_layer[initial_extruder]-20}\nG1 X100 F18000 ; first wipe mouth\n\nG0 X135 Y253 F20000  ; move to exposed steel surface edge\nG28 Z P0 T300; home z with low precision,permit 300deg temperature\nG29.2 S0 ; turn off ABL\nG0 Z5 F20000\n\nG1 X60 Y265\nG92 E0\nG1 E-0.5 F300 ; retrack more\nG1 X100 F5000; second wipe mouth\nG1 X70 F15000\nG1 X100 F5000\nG1 X70 F15000\nG1 X100 F5000\nG1 X70 F15000\nG1 X100 F5000\nG1 X70 F15000\nG1 X90 F5000\nG0 X128 Y261 Z-1.5 F20000  ; move to exposed steel surface and stop the nozzle\nM104 S140 ; set temp down to heatbed acceptable\nM106 S255 ; turn on fan (G28 has turn off fan)\n\nM221 S; push soft endstop status\nM221 Z0 ;turn off Z axis endstop\nG0 Z0.5 F20000\nG0 X125 Y259.5 Z-1.01\nG0 X131 F211\nG0 X124\nG0 Z0.5 F20000\nG0 X125 Y262.5\nG0 Z-1.01\nG0 X131 F211\nG0 X124\nG0 Z0.5 F20000\nG0 X125 Y260.0\nG0 Z-1.01\nG0 X131 F211\nG0 X124\nG0 Z0.5 F20000\nG0 X125 Y262.0\nG0 Z-1.01\nG0 X131 F211\nG0 X124\nG0 Z0.5 F20000\nG0 X125 Y260.5\nG0 Z-1.01\nG0 X131 F211\nG0 X124\nG0 Z0.5 F20000\nG0 X125 Y261.5\nG0 Z-1.01\nG0 X131 F211\nG0 X124\nG0 Z0.5 F20000\nG0 X125 Y261.0\nG0 Z-1.01\nG0 X131 F211\nG0 X124\nG0 X128\nG2 I0.5 J0 F300\nG2 I0.5 J0 F300\nG2 I0.5 J0 F300\nG2 I0.5 J0 F300\n\nM109 S140 ; wait nozzle temp down to heatbed acceptable\nG2 I0.5 J0 F3000\nG2 I0.5 J0 F3000\nG2 I0.5 J0 F3000\nG2 I0.5 J0 F3000\n\nM221 R; pop softend status\nG1 Z10 F1200\nM400\nG1 Z10\nG1 F30000\nG1 X230 Y15\nG29.2 S1 ; turn on ABL\n;G28 ; home again after hard wipe mouth\nM106 S0 ; turn off fan , too noisy\n;===== wipe nozzle end ================================\n\n\n;===== bed leveling ==================================\nM1002 judge_flag g29_before_print_flag\nM622 J1\n\n    M1002 gcode_claim_action : 1\n    G29 A X{first_layer_print_min[0]} Y{first_layer_print_min[1]} I{first_layer_print_size[0]} J{first_layer_print_size[1]}\n    M400\n    M500 ; save cali data\n\nM623\n;===== bed leveling end ================================\n\n;===== home after wipe mouth============================\nM1002 judge_flag g29_before_print_flag\nM622 J0\n\n    M1002 gcode_claim_action : 13\n    G28\n\nM623\n;===== home after wipe mouth end =======================\n\nM975 S1 ; turn on vibration supression\n\n\n;=============turn on fans to prevent PLA jamming=================\n{if filament_type[initial_extruder]=="PLA"}\n    {if (bed_temperature[initial_extruder] >45)||(bed_temperature_initial_layer[initial_extruder] >45)}\n    M106 P3 S180\n    {endif};Prevent PLA from jamming\n{endif}\nM106 P2 S100 ; turn on big fan ,to cool down toolhead\n\n\nM104 S{nozzle_temperature_initial_layer[initial_extruder]} ; set extrude temp earlier, to reduce wait time\n\n;===== mech mode fast check============================\nG1 X128 Y128 Z10 F20000\nM400 P200\nM970.3 Q1 A7 B30 C80  H15 K0\nM974 Q1 S2 P0\n\nG1 X128 Y128 Z10 F20000\nM400 P200\nM970.3 Q0 A7 B30 C90 Q0 H15 K0\nM974 Q0 S2 P0\n\nM975 S1\nG1 F30000\nG1 X230 Y15\nG28 X ; re-home XY\n;===== fmech mode fast check============================\n\n\n;===== nozzle load line ===============================\nM975 S1\nG90\nM83\nT1000\nG1 X18.0 Y1.0 Z0.8 F18000;Move to start position\nM109 S{nozzle_temperature_initial_layer[initial_extruder]}\nG1 Z0.2\nG0 E2 F300\nG0 X240 E15 F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\nG0 Y11 E0.700 F{outer_wall_volumetric_speed/(0.3*0.5)/ 4 * 60}\nG0 X239.5\nG0 E0.2\nG0 Y1.5 E0.700\nG0 X18 E15 F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\nM400\n\n;===== for Textured PEI Plate , lower the nozzle as the nozzle was touching topmost of the texture when homing ==\n;curr_bed_type={curr_bed_type}\n{if curr_bed_type=="Textured PEI Plate"}\nG29.1 Z{-0.04} ; for Textured PEI Plate\n{endif}\n;========turn off light and wait extrude temperature =============\nM1002 gcode_claim_action : 0\nM106 S0 ; turn off fan\nM106 P2 S0 ; turn off big fan\nM106 P3 S0 ; turn off chamber fan\n\nM975 S1 ; turn on mech mode supression\n
; machine_unload_filament_time = 28
; max_bridge_length = 0
; max_layer_height = 0.28
; max_travel_detour_distance = 0
; min_bead_width = 85%
; min_feature_size = 25%
; min_layer_height = 0.08
; minimum_sparse_infill_area = 15
; mmu_segmented_region_interlocking_depth = 0
; mmu_segmented_region_max_width = 0
; nozzle_diameter = 0.4
; nozzle_height = 4.2
; nozzle_temperature = 220,220,220
; nozzle_temperature_initial_layer = 220,220,220
; nozzle_temperature_range_high = 240,240,240
; nozzle_temperature_range_low = 190,190,190
; nozzle_type = stainless_steel
; nozzle_volume = 107
; only_one_wall_first_layer = 0
; ooze_prevention = 0
; other_layers_print_sequence = 0
; other_layers_print_sequence_nums = 0
; outer_wall_acceleration = 5000
; outer_wall_jerk = 9
; outer_wall_line_width = 0.42
; outer_wall_speed = 200
; overhang_1_4_speed = 0
; overhang_2_4_speed = 50
; overhang_3_4_speed = 30
; overhang_4_4_speed = 10
; overhang_fan_speed = 100,100,100
; overhang_fan_threshold = 50%,50%,50%
; overhang_threshold_participating_cooling = 95%,95%,95%
; overhang_totally_speed = 50
; post_process = 
; precise_z_height = 0
; pressure_advance = 0.02,0.02,0.02
; prime_tower_brim_width = 3
; prime_tower_width = 35
; prime_volume = 45
; print_compatible_printers = "Bambu Lab X1 Carbon 0.4 nozzle";"Bambu Lab X1 0.4 nozzle";"Bambu Lab P1S 0.4 nozzle";"Bambu Lab X1E 0.4 nozzle"
; print_flow_ratio = 1
; print_sequence = by layer
; print_settings_id = 0.20mm Standard @BBL X1C
; printable_area = 0x0,256x0,256x256,0x256
; printable_height = 250
; printer_model = Bambu Lab P1S
; printer_notes = 
; printer_settings_id = Bambu Lab P1S 0.4 nozzle
; printer_structure = corexy
; printer_technology = FFF
; printer_variant = 0.4
; printhost_authorization_type = key
; printhost_ssl_ignore_revoke = 0
; printing_by_object_gcode = 
; process_notes = 
; raft_contact_distance = 0.1
; raft_expansion = 1.5
; raft_first_layer_density = 90%
; raft_first_layer_expansion = 2
; raft_layers = 0
; reduce_crossing_wall = 0
; reduce_fan_stop_start_freq = 1,1,1
; reduce_infill_retraction = 1
; required_nozzle_HRC = 3,3,3
; resolution = 0.012
; retract_before_wipe = 0%
; retract_length_toolchange = 2
; retract_lift_above = 0
; retract_lift_below = 249
; retract_restart_extra = 0
; retract_restart_extra_toolchange = 0
; retract_when_changing_layer = 1
; retraction_distances_when_cut = 18
; retraction_length = 0.8
; retraction_minimum_travel = 1
; retraction_speed = 30
; role_base_wipe_speed = 1
; scan_first_layer = 0
; scarf_angle_threshold = 155
; seam_gap = 15%
; seam_position = aligned
; seam_slope_conditional = 1
; seam_slope_entire_loop = 0
; seam_slope_inner_walls = 1
; seam_slope_steps = 10
; silent_mode = 0
; single_extruder_multi_material = 1
; skirt_distance = 2
; skirt_height = 1
; skirt_loops = 0
; slice_closing_radius = 0.049
; slicing_mode = regular
; slow_down_for_layer_cooling = 1,1,1
; slow_down_layer_time = 8,4,8
; slow_down_min_speed = 20,20,20
; small_perimeter_speed = 50%
; small_perimeter_threshold = 0
; smooth_coefficient = 150
; smooth_speed_discontinuity_area = 1
; solid_infill_filament = 1
; sparse_infill_acceleration = 100%
; sparse_infill_anchor = 400%
; sparse_infill_anchor_max = 20
; sparse_infill_density = 15%
; sparse_infill_filament = 1
; sparse_infill_line_width = 0.45
; sparse_infill_pattern = grid
; sparse_infill_speed = 270
; spiral_mode = 0
; spiral_mode_max_xy_smoothing = 200%
; spiral_mode_smooth = 0
; standby_temperature_delta = -5
; start_end_points = 30x-3,54x245
; supertack_plate_temp = 45,45,45
; supertack_plate_temp_initial_layer = 45,45,45
; support_air_filtration = 0
; support_angle = 0
; support_base_pattern = default
; support_base_pattern_spacing = 2.5
; support_bottom_interface_spacing = 0.5
; support_bottom_z_distance = 0.2
; support_chamber_temp_control = 0
; support_critical_regions_only = 0
; support_expansion = 0
; support_filament = 0
; support_interface_bottom_layers = 2
; support_interface_filament = 0
; support_interface_loop_pattern = 0
; support_interface_not_for_body = 1
; support_interface_pattern = auto
; support_interface_spacing = 0.5
; support_interface_speed = 80
; support_interface_top_layers = 2
; support_line_width = 0.42
; support_object_first_layer_gap = 0.2
; support_object_xy_distance = 0.35
; support_on_build_plate_only = 0
; support_remove_small_overhang = 1
; support_speed = 150
; support_style = default
; support_threshold_angle = 30
; support_top_z_distance = 0.2
; support_type = normal(auto)
; temperature_vitrification = 45,45,45
; template_custom_gcode = 
; textured_plate_temp = 55,55,55
; textured_plate_temp_initial_layer = 55,55,55
; thick_bridges = 0
; thumbnail_size = 50x50
; time_lapse_gcode = 
; timelapse_type = 0
; top_area_threshold = 100%
; top_one_wall_type = all top
; top_shell_layers = 5
; top_shell_thickness = 1
; top_solid_infill_flow_ratio = 1
; top_surface_acceleration = 2000
; top_surface_jerk = 9
; top_surface_line_width = 0.42
; top_surface_pattern = monotonicline
; top_surface_speed = 200
; travel_jerk = 9
; travel_speed = 500
; travel_speed_z = 0
; tree_support_branch_angle = 45
; tree_support_branch_diameter = 2
; tree_support_branch_diameter_angle = 5
; tree_support_branch_distance = 5
; tree_support_wall_count = 0
; upward_compatible_machine = "Bambu Lab P1P 0.4 nozzle";"Bambu Lab X1 0.4 nozzle";"Bambu Lab X1 Carbon 0.4 nozzle";"Bambu Lab X1E 0.4 nozzle";"Bambu Lab A1 0.4 nozzle"
; use_firmware_retraction = 0
; use_relative_e_distances = 1
; wall_distribution_count = 1
; wall_filament = 1
; wall_generator = classic
; wall_loops = 2
; wall_sequence = inner wall/outer wall
; wall_transition_angle = 10
; wall_transition_filter_deviation = 25%
; wall_transition_length = 100%
; wipe = 1
; wipe_distance = 2
; wipe_speed = 80%
; wipe_tower_no_sparse_layers = 0
; wipe_tower_rotation_angle = 0
; wipe_tower_x = 165
; wipe_tower_y = 241
; xy_contour_compensation = 0
; xy_hole_compensation = 0
; z_hop = 0.4
; z_hop_types = Auto Lift
; CONFIG_BLOCK_END

; EXECUTABLE_BLOCK_START
M73 P0 R7
M201 X20000 Y20000 Z500 E5000
M203 X500 Y500 Z20 E30
M204 P20000 R5000 T20000
M205 X9.00 Y9.00 Z3.00 E2.50
M106 S0
M106 P2 S0
; FEATURE: Custom
;===== machine: P1S ========================
;===== date: 20231107 =====================
;===== turn on the HB fan & MC board fan =================
M104 S75 ;set extruder temp to turn on the HB fan and prevent filament oozing from nozzle
M710 A1 S255 ;turn on MC fan by default(P1S)
;===== reset machine status =================
M290 X40 Y40 Z2.6666666
G91
M17 Z0.4 ; lower the z-motor current
G380 S2 Z30 F300 ; G380 is same as G38; lower the hotbed , to prevent the nozzle is below the hotbed
G380 S2 Z-25 F300 ;
G1 Z5 F300;
G90
M17 X1.2 Y1.2 Z0.75 ; reset motor current to default
M960 S5 P1 ; turn on logo lamp
G90
M220 S100 ;Reset Feedrate
M221 S100 ;Reset Flowrate
M73.2   R1.0 ;Reset left time magnitude
M1002 set_gcode_claim_speed_level : 5
M221 X0 Y0 Z0 ; turn off soft endstop to prevent protential logic problem
G29.1 Z0 ; clear z-trim value first
M204 S10000 ; init ACC set to 10m/s^2

;===== heatbed preheat ====================
M1002 gcode_claim_action : 2
M140 S55 ;set bed temp
M190 S55 ;wait for bed temp



;=============turn on fans to prevent PLA jamming=================

    
    M106 P3 S180
    ;Prevent PLA from jamming

M106 P2 S100 ; turn on big fan ,to cool down toolhead

;===== prepare print temperature and material ==========
M104 S220 ;set extruder temp
G91
G0 Z10 F1200
G90
G28 X
M975 S1 ; turn on
M73 P6 R6
G1 X60 F12000
M73 P7 R6
G1 Y245
G1 Y265 F3000
M620 M
M620 S1A   ; switch material if AMS exist
    M109 S220
    G1 X120 F12000

    G1 X20 Y50 F12000
    G1 Y-3
    T1
    G1 X54 F12000
    G1 Y265
    M400
M621 S1A
M620.1 E F523.843 T240


M412 S1 ; ===turn on filament runout detection===

M109 S250 ;set nozzle to common flush temp
M106 P1 S0
G92 E0
G1 E50 F200
M400
M104 S220
G92 E0
M73 P67 R2
G1 E50 F200
M400
M106 P1 S255
G92 E0
G1 E5 F300
M109 S200 ; drop nozzle temp, make filament shink a bit
G92 E0
M73 P71 R2
G1 E-0.5 F300

M73 P74 R1
G1 X70 F9000
G1 X76 F15000
G1 X65 F15000
M73 P75 R1
G1 X76 F15000
G1 X65 F15000; shake to put down garbage
G1 X80 F6000
G1 X95 F15000
G1 X80 F15000
G1 X165 F15000; wipe and shake
M400
M106 P1 S0
;===== prepare print temperature and material end =====


;===== wipe nozzle ===============================
M1002 gcode_claim_action : 14
M975 S1
M106 S255
G1 X65 Y230 F18000
G1 Y264 F6000
M109 S200
G1 X100 F18000 ; first wipe mouth

G0 X135 Y253 F20000  ; move to exposed steel surface edge
G28 Z P0 T300; home z with low precision,permit 300deg temperature
G29.2 S0 ; turn off ABL
G0 Z5 F20000

G1 X60 Y265
G92 E0
G1 E-0.5 F300 ; retrack more
G1 X100 F5000; second wipe mouth
G1 X70 F15000
G1 X100 F5000
G1 X70 F15000
G1 X100 F5000
G1 X70 F15000
G1 X100 F5000
G1 X70 F15000
M73 P76 R1
G1 X90 F5000
G0 X128 Y261 Z-1.5 F20000  ; move to exposed steel surface and stop the nozzle
M104 S140 ; set temp down to heatbed acceptable
M106 S255 ; turn on fan (G28 has turn off fan)

M221 S; push soft endstop status
M221 Z0 ;turn off Z axis endstop
G0 Z0.5 F20000
G0 X125 Y259.5 Z-1.01
G0 X131 F211
G0 X124
G0 Z0.5 F20000
G0 X125 Y262.5
G0 Z-1.01
G0 X131 F211
G0 X124
G0 Z0.5 F20000
G0 X125 Y260.0
G0 Z-1.01
G0 X131 F211
G0 X124
G0 Z0.5 F20000
G0 X125 Y262.0
G0 Z-1.01
G0 X131 F211
G0 X124
G0 Z0.5 F20000
G0 X125 Y260.5
G0 Z-1.01
G0 X131 F211
G0 X124
G0 Z0.5 F20000
G0 X125 Y261.5
G0 Z-1.01
G0 X131 F211
G0 X124
G0 Z0.5 F20000
G0 X125 Y261.0
G0 Z-1.01
G0 X131 F211
G0 X124
G0 X128
G2 I0.5 J0 F300
G2 I0.5 J0 F300
G2 I0.5 J0 F300
G2 I0.5 J0 F300

M109 S140 ; wait nozzle temp down to heatbed acceptable
G2 I0.5 J0 F3000
G2 I0.5 J0 F3000
G2 I0.5 J0 F3000
G2 I0.5 J0 F3000

M221 R; pop softend status
G1 Z10 F1200
M400
G1 Z10
M73 P77 R1
G1 F30000
G1 X230 Y15
G29.2 S1 ; turn on ABL
;G28 ; home again after hard wipe mouth
M106 S0 ; turn off fan , too noisy
;===== wipe nozzle end ================================


;===== bed leveling ==================================
M1002 judge_flag g29_before_print_flag
M622 J1

    M1002 gcode_claim_action : 1
    G29 A X107.261 Y123.189 I41.4789 J9.62286
    M400
    M500 ; save cali data

M623
;===== bed leveling end ================================

;===== home after wipe mouth============================
M1002 judge_flag g29_before_print_flag
M622 J0

    M1002 gcode_claim_action : 13
    G28

M623
;===== home after wipe mouth end =======================

M975 S1 ; turn on vibration supression


;=============turn on fans to prevent PLA jamming=================

    
    M106 P3 S180
    ;Prevent PLA from jamming

M106 P2 S100 ; turn on big fan ,to cool down toolhead


M104 S220 ; set extrude temp earlier, to reduce wait time

;===== mech mode fast check============================
G1 X128 Y128 Z10 F20000
M400 P200
M970.3 Q1 A7 B30 C80  H15 K0
M974 Q1 S2 P0

G1 X128 Y128 Z10 F20000
M400 P200
M970.3 Q0 A7 B30 C90 Q0 H15 K0
M974 Q0 S2 P0

M975 S1
G1 F30000
M73 P78 R1
G1 X230 Y15
G28 X ; re-home XY
;===== fmech mode fast check============================


;===== nozzle load line ===============================
M975 S1
G90
M83
T1000
G1 X18.0 Y1.0 Z0.8 F18000;Move to start position
M109 S220
G1 Z0.2
G0 E2 F300
G0 X240 E15 F6033.27
G0 Y11 E0.700 F1508.32
G0 X239.5
G0 E0.2
G0 Y1.5 E0.700
G0 X18 E15 F6033.27
M400

;===== for Textured PEI Plate , lower the nozzle as the nozzle was touching topmost of the texture when homing ==
;curr_bed_type=Textured PEI Plate

G29.1 Z-0.04 ; for Textured PEI Plate

;========turn off light and wait extrude temperature =============
M1002 gcode_claim_action : 0
M106 S0 ; turn off fan
M106 P2 S0 ; turn off big fan
M106 P3 S0 ; turn off chamber fan

M975 S1 ; turn on mech mode supression
G90
G21
M83 ; use relative distances for extrusion
M620 S1A
M204 S9000

G1 Z3 F1200

G1 X70 F21000
M73 P79 R1
G1 Y245
G1 Y265 F3000
M400
M106 P1 S0
M106 P2 S0

M104 S220


M620.11 S1 I1 E-18 F523

M400
G1 X90 F3000
G1 Y255 F4000
G1 X100 F5000
M73 P80 R1
G1 X120 F15000
G1 X20 Y50 F21000
G1 Y-3

M620.1 E F523 T240
T1
M620.1 E F523 T240



M620.11 S1 I1 E18 F523
M628 S1
G92 E0
G1 E18 F523
M400
M629 S1

G92 E0







; FLUSH_START
M400
M109 S220
G1 E2 F523 ;Compensate for filament spillage during waiting temperature
; FLUSH_END
M400
G92 E0
G1 E-2 F1800
M106 P1 S255
M400 S3

G1 X70 F5000
G1 X90 F3000
G1 Y255 F4000
M73 P81 R1
G1 X105 F5000
G1 Y265 F5000
G1 X70 F10000
G1 X100 F5000
G1 X70 F10000
M73 P82 R1
G1 X100 F5000

G1 X70 F10000
G1 X80 F15000
M73 P83 R1
G1 X60
G1 X80
G1 X60
G1 X80 ; shake to put down garbage
G1 X100 F5000
G1 X165 F15000; wipe and shake
G1 Y256 ; move Y to aside, prevent collision
M400
G1 Z3 F3000

M204 S500


M621 S1A
;_FORCE_RESUME_FAN_SPEED
M104 S220 ; set nozzle temperature
; filament start gcode
M106 P3 S150

M142 P1 R35 S40
M981 S1 P20000 ;open spaghetti detector
; CHANGE_LAYER
; Z_HEIGHT: 0.2
; LAYER_HEIGHT: 0.2
G1 E-.8 F1800
; layer num/total_layer_count: 1/5
M622.1 S1 ; for prev firware, default turned on
M1002 judge_flag timelapse_record_flag
M622 J1
 ; timelapse without wipe tower
M971 S11 C10 O0
M1004 S5 P1  ; external shutter

M623
; update layer progress
M73 L1
M991 S0 P0 ;notify layer change
M106 S0
M106 P2 S0
M204 S500
G1 X133.982 Y123.178 F30000
G1 Z3.4
G1 Z.2
M73 P84 R1
G1 E.8 F1800
; FEATURE: Outer wall
; LINE_WIDTH: 0.5
G1 F3000
G1 X134.137 Y123.208 E.00584
G1 X134.137 Y123.249 E.00154
G1 X133.982 Y123.279 E.00584
M73 P85 R1
G1 X116.133 Y123.279 E.66484
G2 X116.133 Y128.721 I.018 J2.721 E.31712
G1 X144.711 Y128.721 E1.06444
G2 X144.711 Y121.749 I-.016 J-3.486 E.40673
G1 X112.055 Y121.749 E1.21633
G2 X112.055 Y130.251 I.016 J4.251 E.49627
G1 X133.98 Y130.251 E.81664
G1 X134.136 Y130.281 E.00593
G1 X134.136 Y130.322 E.00152
M73 P86 R0
G1 X133.98 Y130.352 E.00593
G1 X112.07 Y130.352 E.81606
G3 X112.07 Y121.648 I-.004 J-4.352 E.50949
G1 X144.694 Y121.648 E1.21511
G1 X145.012 Y121.67 E.01188
G1 X145.191 Y121.682 E.00666
G3 X148.238 Y125.787 I-.502 J3.556 E.21188
G1 X148.214 Y125.965 E.00666
M73 P87 R0
G3 X144.694 Y128.822 I-3.536 J-.76 E.18248
G1 X116.152 Y128.822 E1.06307
G3 X116.152 Y123.178 I-.005 J-2.822 E.33053
G1 X133.922 Y123.178 E.66187
; CHANGE_LAYER
; Z_HEIGHT: 0.4
; LAYER_HEIGHT: 0.2
; WIPE_START
G1 F3000
G1 X134.137 Y123.208 E-.08212
G1 X134.137 Y123.249 E-.01571
G1 X133.982 Y123.279 E-.05961
M73 P88 R0
G1 X132.397 Y123.279 E-.60256
; WIPE_END
G1 E-.04 F1800
; layer num/total_layer_count: 2/5
M622.1 S1 ; for prev firware, default turned on
M1002 judge_flag timelapse_record_flag
M622 J1
 ; timelapse without wipe tower
M971 S11 C10 O0
M1004 S5 P1  ; external shutter

M623
; update layer progress
M73 L2
M991 S0 P1 ;notify layer change
M106 S255
M106 P2 S178
; open powerlost recovery
M1003 S1
M204 S10000
G17
G3 Z.6 I.116 J1.211 P1  F30000
M73 P89 R0
G1 X134.292 Y123.097 Z.6
G1 Z.4
G1 E.8 F1800
M204 S5000
; LINE_WIDTH: 0.42
G1 F5639.921
G1 X134.292 Y123.36 E.00806
G1 F2520
G1 X134.292 Y123.481 E.00373
G1 X116.134 Y123.481 E.55795
G2 X116.134 Y128.519 I.013 J2.519 E.24234
G1 X144.71 Y128.519 E.87804
G2 X144.71 Y121.951 I-.007 J-3.284 E.31658
G1 X112.056 Y121.951 E1.00336
G2 X112.056 Y130.049 I.014 J4.049 E.38997
G1 X134.292 Y130.049 E.68327
G1 F3809.222
G1 X134.292 Y130.17 E.00373
G1 F4679.812
G1 X134.292 Y130.433 E.00806
G1 F2520
G1 X134.292 Y130.554 E.00373
G1 X112.069 Y130.554 E.68286
G3 X112.069 Y121.446 I-.003 J-4.554 E.43982
G1 X144.695 Y121.446 E1.00251
G1 X144.994 Y121.466 E.00919
G1 X145.218 Y121.482 E.00692
M73 P90 R0
G3 X144.695 Y129.024 I-.526 J3.753 E.34953
G1 X116.151 Y129.024 E.87709
G3 X116.151 Y122.976 I-.004 J-3.024 E.29217
G1 X134.292 Y122.976 E.55745
G1 F3139.012
G1 X134.292 Y123.037 E.00189
M204 S10000
G1 X134.096 Y123.229 F30000
; FEATURE: Gap infill
; LINE_WIDTH: 0.15561
G1 F15000
G1 X116.161 Y123.229 E.1647
G1 X115.709 Y123.263 E.00416
G1 X115.286 Y123.364 E.00399
G1 X114.881 Y123.533 E.00403
G1 X114.514 Y123.758 E.00395
G1 X114.186 Y124.037 E.00395
G1 X113.9 Y124.371 E.00403
G1 X113.673 Y124.742 E.00399
G1 X113.506 Y125.148 E.00403
M73 P91 R0
G1 X113.405 Y125.566 E.00395
G1 X113.371 Y125.996 E.00395
G1 X113.405 Y126.434 E.00403
G1 X113.507 Y126.856 E.00399
G1 X113.673 Y127.258 E.00399
G1 X113.9 Y127.629 E.00399
G1 X114.186 Y127.963 E.00403
G1 X114.514 Y128.242 E.00395
G1 X114.888 Y128.471 E.00403
G1 X115.29 Y128.637 E.00399
G1 X115.709 Y128.737 E.00395
G1 X116.122 Y128.77 E.00381
G1 X144.687 Y128.771 E.2623
G1 X145.184 Y128.738 E.00458
G1 X145.66 Y128.639 E.00447
G1 X146.111 Y128.479 E.0044
G1 X146.537 Y128.258 E.0044
G1 X146.934 Y127.978 E.00447
G1 X147.289 Y127.646 E.00447
G1 X147.592 Y127.274 E.0044
G1 X147.84 Y126.865 E.0044
G1 X148.035 Y126.419 E.00447
G1 X148.165 Y125.954 E.00443
G1 X148.231 Y125.476 E.00443
G1 X148.231 Y124.997 E.0044
G1 X148.164 Y124.512 E.0045
G1 X148.035 Y124.051 E.0044
G1 X147.842 Y123.608 E.00443
G1 X147.592 Y123.196 E.00443
M73 P92 R0
G1 X147.289 Y122.824 E.0044
G1 X146.931 Y122.49 E.0045
G1 X146.54 Y122.213 E.0044
G1 X146.111 Y121.991 E.00443
G1 X145.657 Y121.83 E.00443
G1 X145.188 Y121.732 E.0044
G1 X144.687 Y121.699 E.00461
G1 X112.077 Y121.699 E.29945
G1 X111.523 Y121.733 E.00509
G1 X110.993 Y121.834 E.00496
G1 X110.482 Y122 E.00493
G1 X109.99 Y122.231 E.00499
G1 X109.531 Y122.522 E.00499
G1 X109.118 Y122.864 E.00493
G1 X108.751 Y123.256 E.00493
G1 X108.431 Y123.695 E.00499
G1 X108.169 Y124.172 E.00499
G1 X107.972 Y124.671 E.00493
G1 X107.838 Y125.191 E.00493
G1 X107.77 Y125.733 E.00502
G1 X107.77 Y126.27 E.00493
G1 X107.837 Y126.803 E.00493
G1 X107.972 Y127.329 E.00499
G1 X108.17 Y127.831 E.00496
G1 X108.429 Y128.302 E.00493
G1 X108.748 Y128.742 E.00499
G1 X109.118 Y129.136 E.00496
G1 X109.531 Y129.478 E.00493
G1 X109.99 Y129.769 E.00499
G1 X110.482 Y130 E.00499
G1 X110.993 Y130.166 E.00493
G1 X111.523 Y130.267 E.00496
G1 X112.077 Y130.301 E.00509
G1 X134.096 Y130.301 E.2022
; CHANGE_LAYER
; Z_HEIGHT: 0.6
; LAYER_HEIGHT: 0.2
; WIPE_START
G1 F15000
G1 X132.096 Y130.301 E-.76
; WIPE_END
G1 E-.04 F1800
; layer num/total_layer_count: 3/5
M622.1 S1 ; for prev firware, default turned on
M1002 judge_flag timelapse_record_flag
M622 J1
 ; timelapse without wipe tower
M971 S11 C10 O0
M1004 S5 P1  ; external shutter

M623
; update layer progress
M73 L3
M991 S0 P2 ;notify layer change
G17
G3 Z.8 I.164 J1.206 P1  F30000
G1 X134.292 Y130.002 Z.8
G1 Z.6
G1 E.8 F1800
M204 S5000
; FEATURE: Outer wall
; LINE_WIDTH: 0.42
G1 F6186
G1 X134.292 Y130.008 E.00017
G1 X134.292 Y130.595 E.01805
G1 X112.069 Y130.601 E.68286
G3 X112.069 Y121.399 I0 J-4.601 E.44413
G1 X144.695 Y121.399 E1.00251
G1 X145.177 Y121.432 E.01483
G1 X145.225 Y121.436 E.00147
G3 X144.695 Y129.071 I-.532 J3.799 E.35381
G1 X116.151 Y129.071 E.87709
G3 X116.151 Y122.929 I-.003 J-3.071 E.2966
G1 X134.292 Y122.929 E.55745
G1 X134.292 Y122.935 E.00017
G1 X134.292 Y123.522 E.01805
G1 X116.134 Y123.528 E.55795
G2 X116.134 Y128.472 I.014 J2.472 E.23783
G1 X144.71 Y128.472 E.87804
G2 X144.71 Y121.998 I-.011 J-3.237 E.31181
G1 X112.056 Y121.998 E1.00336
G2 X112.056 Y130.002 I.011 J4.002 E.38566
G1 X134.232 Y130.002 E.68143
M204 S10000
G1 X134.096 Y130.301 F30000
; FEATURE: Gap infill
; LINE_WIDTH: 0.248493
G1 F6186
G1 X112.078 Y130.301 E.36883
G1 X111.523 Y130.267 E.00932
G1 X110.993 Y130.166 E.00905
G1 X110.485 Y130.001 E.00894
G1 X109.99 Y129.769 E.00916
G1 X109.529 Y129.476 E.00916
G1 X109.118 Y129.136 E.00894
G1 X108.748 Y128.742 E.00905
G1 X108.431 Y128.305 E.00905
G1 X108.174 Y127.837 E.00894
G1 X107.972 Y127.329 E.00916
G1 X107.836 Y126.8 E.00916
G1 X107.77 Y126.27 E.00894
G1 X107.77 Y125.736 E.00894
G1 X107.837 Y125.194 E.00916
G1 X107.974 Y124.665 E.00916
G1 X108.171 Y124.169 E.00894
G1 X108.428 Y123.701 E.00894
G1 X108.753 Y123.253 E.00926
G1 X109.118 Y122.864 E.00894
G1 X109.529 Y122.524 E.00894
G1 X109.99 Y122.231 E.00916
G1 X110.485 Y121.999 E.00916
G1 X110.993 Y121.834 E.00894
G1 X111.523 Y121.733 E.00905
G1 X112.078 Y121.699 E.00932
G1 X144.685 Y121.699 E.54621
G1 X145.191 Y121.733 E.00849
G1 X145.657 Y121.83 E.00797
G1 X146.111 Y121.991 E.00809
G1 X146.54 Y122.214 E.00809
G1 X146.929 Y122.488 E.00797
G1 X147.291 Y122.827 E.00832
M73 P93 R0
G1 X147.592 Y123.196 E.00797
G1 X147.842 Y123.608 E.00809
G1 X148.035 Y124.051 E.00809
G1 X148.163 Y124.509 E.00797
G1 X148.231 Y125.001 E.00832
G1 X148.231 Y125.476 E.00797
G1 X148.165 Y125.954 E.00809
G1 X148.035 Y126.419 E.00809
G1 X147.839 Y126.868 E.0082
G1 X147.592 Y127.274 E.00797
G1 X147.291 Y127.643 E.00797
G1 X146.934 Y127.978 E.0082
G1 X146.534 Y128.26 E.0082
G1 X146.111 Y128.479 E.00797
G1 X145.663 Y128.638 E.00797
G1 X145.184 Y128.738 E.0082
G1 X144.685 Y128.771 E.00838
G1 X116.119 Y128.77 E.47853
G1 X115.709 Y128.737 E.00688
G1 X115.294 Y128.638 E.00715
G1 X114.892 Y128.472 E.00728
G1 X114.514 Y128.242 E.00742
G1 X114.189 Y127.965 E.00715
G1 X113.9 Y127.629 E.00742
G1 X113.673 Y127.258 E.00728
G1 X113.507 Y126.856 E.00728
G1 X113.405 Y126.434 E.00728
G1 X113.371 Y126 E.00728
G1 X113.407 Y125.559 E.00742
G1 X113.507 Y125.144 E.00715
G1 X113.67 Y124.749 E.00715
G1 X113.9 Y124.371 E.00742
G1 X114.189 Y124.035 E.00742
M73 P94 R0
G1 X114.514 Y123.758 E.00715
G1 X114.877 Y123.535 E.00715
G1 X115.286 Y123.364 E.00742
G1 X115.709 Y123.263 E.00728
G1 X116.162 Y123.229 E.00762
G1 X134.096 Y123.229 E.30042
; CHANGE_LAYER
; Z_HEIGHT: 0.8
; LAYER_HEIGHT: 0.2
; WIPE_START
G1 F15000
G1 X132.096 Y123.229 E-.76
; WIPE_END
G1 E-.04 F1800
; layer num/total_layer_count: 4/5
M622.1 S1 ; for prev firware, default turned on
M1002 judge_flag timelapse_record_flag
M622 J1
 ; timelapse without wipe tower
M971 S11 C10 O0
M1004 S5 P1  ; external shutter

M623
; update layer progress
M73 L4
M991 S0 P3 ;notify layer change
G17
G3 Z1 I-1.158 J.373 P1  F30000
G1 X134.292 Y130.039 Z1
G1 Z.8
G1 E.8 F1800
M204 S5000
; FEATURE: Outer wall
; LINE_WIDTH: 0.42
G1 F6199
G1 X134.292 Y130.563 E.0161
G1 X112.069 Y130.563 E.68286
G3 X112.069 Y121.437 I-.003 J-4.563 E.44072
G1 X144.793 Y121.443 E1.00551
G3 X144.695 Y129.033 I-.094 J3.794 E.36364
G1 X116.151 Y129.033 E.87709
G3 X116.151 Y122.967 I-.001 J-3.033 E.29287
G1 X134.292 Y122.967 E.55745
G1 X134.292 Y123.491 E.0161
G1 X116.134 Y123.491 E.55795
G2 X116.134 Y128.509 I.015 J2.509 E.2413
G1 X144.71 Y128.509 E.87804
G2 X144.71 Y121.961 I-.014 J-3.274 E.31521
G1 X112.056 Y121.961 E1.00336
G2 X112.056 Y130.039 I.014 J4.039 E.38907
G1 X134.232 Y130.039 E.68143
M204 S10000
G1 X134.096 Y130.301 F30000
; FEATURE: Gap infill
; LINE_WIDTH: 0.174252
G1 F6199
G1 X112.077 Y130.301 E.23565
G1 X111.523 Y130.267 E.00594
G1 X110.993 Y130.166 E.00578
G1 X110.483 Y130.001 E.00574
G1 X109.99 Y129.769 E.00582
G1 X109.531 Y129.477 E.00582
G1 X109.118 Y129.136 E.00574
G1 X108.748 Y128.742 E.00578
G1 X108.431 Y128.305 E.00578
G1 X108.172 Y127.835 E.00574
G1 X107.972 Y127.329 E.00582
G1 X107.837 Y126.802 E.00582
G1 X107.77 Y126.27 E.00574
G1 X107.77 Y125.734 E.00574
G1 X107.838 Y125.19 E.00587
G1 X107.972 Y124.671 E.00574
G1 X108.169 Y124.172 E.00574
G1 X108.431 Y123.695 E.00582
G1 X108.751 Y123.255 E.00582
G1 X109.118 Y122.864 E.00574
G1 X109.531 Y122.523 E.00574
G1 X109.99 Y122.231 E.00582
G1 X110.479 Y122.001 E.00578
G1 X110.875 Y121.872 E.00446
G1 X110.993 Y121.834 E.00132
G1 X111.523 Y121.733 E.00578
G1 X112.077 Y121.699 E.00594
G1 X144.686 Y121.699 E.34898
G1 X145.188 Y121.732 E.00538
G1 X145.657 Y121.83 E.00512
G1 X146.111 Y121.991 E.00517
G1 X146.54 Y122.213 E.00517
G1 X146.931 Y122.489 E.00512
G1 X147.29 Y122.825 E.00526
G1 X147.592 Y123.196 E.00512
G1 X147.842 Y123.608 E.00517
G1 X148.035 Y124.051 E.00517
G1 X148.164 Y124.511 E.00512
G1 X148.231 Y124.998 E.00526
G1 X148.231 Y125.476 E.00512
G1 X148.165 Y125.954 E.00517
G1 X148.035 Y126.419 E.00517
G1 X147.84 Y126.866 E.00521
G1 X147.592 Y127.274 E.00512
M73 P95 R0
G1 X147.29 Y127.645 E.00512
G1 X146.934 Y127.978 E.00521
G1 X146.536 Y128.259 E.00521
G1 X146.111 Y128.479 E.00512
G1 X145.661 Y128.639 E.00512
G1 X145.184 Y128.738 E.00521
G1 X144.686 Y128.771 E.00534
G1 X116.121 Y128.77 E.3057
G1 X115.709 Y128.737 E.00443
G1 X115.291 Y128.637 E.0046
G1 X114.889 Y128.471 E.00465
G1 X114.514 Y128.242 E.00471
G1 X114.187 Y127.963 E.0046
G1 X113.9 Y127.629 E.00471
G1 X113.673 Y127.258 E.00465
G1 X113.507 Y126.856 E.00465
G1 X113.405 Y126.434 E.00465
G1 X113.371 Y125.995 E.00471
G1 X113.405 Y125.566 E.0046
G1 X113.505 Y125.149 E.0046
G1 X113.673 Y124.742 E.00471
G1 X113.9 Y124.371 E.00465
G1 X114.183 Y124.04 E.00465
G1 X114.518 Y123.755 E.00471
G1 X114.884 Y123.531 E.0046
G1 X115.281 Y123.366 E.0046
G1 X115.709 Y123.263 E.00471
G1 X116.161 Y123.229 E.00485
G1 X134.096 Y123.229 E.19194
; CHANGE_LAYER
; Z_HEIGHT: 1
; LAYER_HEIGHT: 0.2
; WIPE_START
G1 F15000
G1 X132.096 Y123.229 E-.76
; WIPE_END
G1 E-.04 F1800
; layer num/total_layer_count: 5/5
M622.1 S1 ; for prev firware, default turned on
M1002 judge_flag timelapse_record_flag
M622 J1
 ; timelapse without wipe tower
M971 S11 C10 O0
M1004 S5 P1  ; external shutter

M623
; update layer progress
M73 L5
M991 S0 P4 ;notify layer change
G17
G3 Z1.2 I.066 J1.215 P1  F30000
G1 X134.292 Y123.11 Z1.2
G1 Z1
G1 E.8 F1800
M204 S5000
; FEATURE: Outer wall
; LINE_WIDTH: 0.42
G1 F4119
G1 X134.292 Y123.347 E.00728
G1 X116.134 Y123.347 E.55795
G2 X116.134 Y128.653 I.008 J2.653 E.25563
G1 X144.71 Y128.653 E.87804
G2 X144.71 Y121.817 I-.015 J-3.418 E.32904
G1 X112.056 Y121.817 E1.00336
G2 X112.056 Y130.183 I.014 J4.183 E.4029
G1 X134.292 Y130.183 E.68327
G1 X134.292 Y130.42 E.00728
G1 X112.069 Y130.42 E.68286
G3 X112.069 Y121.58 I.003 J-4.42 E.42651
G1 X144.695 Y121.58 E1.00251
G1 X145.194 Y121.614 E.01537
G3 X144.695 Y128.89 I-.496 J3.621 E.33764
G1 X116.151 Y128.89 E.87709
G3 X116.151 Y123.11 I-.004 J-2.89 E.27922
G1 X134.232 Y123.11 E.5556
M204 S10000
; close powerlost recovery
M1003 S0
; WIPE_START
G1 F12000
G1 X134.292 Y123.347 E-.0929
G1 X132.537 Y123.347 E-.6671
; WIPE_END
G1 E-.04 F1800
M106 S0
M106 P2 S0
M981 S0 P20000 ; close spaghetti detector
; FEATURE: Custom
; filament end gcode 
M106 P3 S0
;===== date: 20230428 =====================
M400 ; wait for buffer to clear
G92 E0 ; zero the extruder
G1 E-0.8 F1800 ; retract
G1 Z1.5 F900 ; lower z a little
G1 X65 Y245 F12000 ; move to safe pos 
G1 Y265 F3000

G1 X65 Y245 F12000
G1 Y265 F3000
M140 S0 ; turn off bed
M106 S0 ; turn off fan
M106 P2 S0 ; turn off remote part cooling fan
M106 P3 S0 ; turn off chamber cooling fan

G1 X100 F12000 ; wipe
; pull back filament to AMS
M620 S255
G1 X20 Y50 F12000
G1 Y-3
T255
G1 X65 F12000
G1 Y265
G1 X100 F12000 ; wipe
M621 S255
M104 S0 ; turn off hotend

M622.1 S1 ; for prev firware, default turned on
M1002 judge_flag timelapse_record_flag
M622 J1
    M400 ; wait all motion done
    M991 S0 P-1 ;end smooth timelapse at safe pos
    M400 S3 ;wait for last picture to be taken
M623; end of "timelapse_record_flag"

M400 ; wait all motion done
M17 S
M17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom

    G1 Z101 F600
    G1 Z99

M400 P100
M17 R ; restore z current

M220 S100  ; Reset feedrate magnitude
M201.2 K1.0 ; Reset acc magnitude
M73.2   R1.0 ;Reset left time magnitude
M1002 set_gcode_claim_speed_level : 0

M17 X0.8 Y0.8 Z0.5 ; lower motor current to 45% power
M73 P100 R0
; EXECUTABLE_BLOCK_END

