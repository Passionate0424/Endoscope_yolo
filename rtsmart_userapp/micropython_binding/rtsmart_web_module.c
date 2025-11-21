/*
 * MicroPython 绑定模块 - RT-Smart Web Server
 * 将 MicroPython YOLO 管线与 C 侧 HTTP 服务器联动
 */

#include "py/obj.h"
#include "py/runtime.h"
#include "py/objstr.h"
#include "py/mperrno.h"

#include <rtthread.h>

#include "frame_buffer.h"
#include "web_state.h"
#include "config.h"

static void ensure_frame_buffer_ready(void)
{
    if (!frame_buffer_is_ready())
    {
        frame_buffer_init(FRAME_BUFFER_QUALITY);
    }
}

STATIC mp_obj_t rtsmart_web_push_frame(mp_obj_t jpeg_bytes_obj)
{
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(jpeg_bytes_obj, &bufinfo, MP_BUFFER_READ);

    ensure_frame_buffer_ready();
    if (frame_buffer_push((const uint8_t *)bufinfo.buf, bufinfo.len) != 0)
    {
        mp_raise_OSError(MP_EIO);
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(rtsmart_web_push_frame_obj, rtsmart_web_push_frame);

STATIC mp_obj_t rtsmart_web_is_ready(void)
{
    return mp_obj_new_bool(1);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(rtsmart_web_is_ready_obj, rtsmart_web_is_ready);

STATIC mp_obj_t rtsmart_web_get_control(void)
{
    web_control_info_t info;
    web_state_get_control_info(&info);

    mp_obj_t dict = mp_obj_new_dict(7);
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_camera_desired), mp_obj_new_bool(info.desired_camera_running));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_camera_running), mp_obj_new_bool(info.actual_camera_running));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_detection_desired), mp_obj_new_bool(info.desired_detection_enabled));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_detection_enabled), mp_obj_new_bool(info.actual_detection_enabled));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_confidence_desired), mp_obj_new_float(info.desired_confidence));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_confidence_actual), mp_obj_new_float(info.actual_confidence));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_command_version), mp_obj_new_int(info.command_version));
    return dict;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(rtsmart_web_get_control_obj, rtsmart_web_get_control);

STATIC mp_obj_t rtsmart_web_set_runtime(size_t n_args, const mp_obj_t *args)
{
    rt_bool_t cam = mp_obj_is_true(args[0]);
    rt_bool_t det = mp_obj_is_true(args[1]);
    web_state_set_camera_running(cam);
    web_state_set_detection_enabled(det);
    if (n_args >= 3)
    {
        float conf = mp_obj_get_float(args[2]);
        web_state_set_confidence(conf);
    }
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rtsmart_web_set_runtime_obj, 2, 3, rtsmart_web_set_runtime);

STATIC mp_obj_t rtsmart_web_set_stats(size_t n_args, const mp_obj_t *args)
{
    uint32_t frames = mp_obj_get_int(args[0]);
    uint32_t detections = mp_obj_get_int(args[1]);
    float fps = mp_obj_get_float(args[2]);
    web_state_update_stats(frames, detections, fps);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rtsmart_web_set_stats_obj, 3, 3, rtsmart_web_set_stats);

STATIC mp_obj_t rtsmart_web_add_record(size_t n_args, const mp_obj_t *args)
{
    const char *filename = mp_obj_str_get_str(args[0]);
    const char *time_str = mp_obj_str_get_str(args[1]);
    float confidence = mp_obj_get_float(args[2]);
    web_state_add_record(filename, time_str, confidence);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rtsmart_web_add_record_obj, 3, 3, rtsmart_web_add_record);

STATIC mp_obj_t rtsmart_web_delete_record(mp_obj_t id_obj)
{
    uint32_t id = (uint32_t)mp_obj_get_int(id_obj);
    web_state_delete_record(id);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(rtsmart_web_delete_record_obj, rtsmart_web_delete_record);

STATIC mp_obj_t rtsmart_web_clear_records(void)
{
    web_state_clear_records();
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(rtsmart_web_clear_records_obj, rtsmart_web_clear_records);

STATIC mp_obj_t rtsmart_web_get_stats(void)
{
    web_stats_info_t stats;
    web_state_get_stats(&stats);
    mp_obj_t dict = mp_obj_new_dict(3);
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_total_frames), mp_obj_new_int(stats.total_frames));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_total_detections), mp_obj_new_int(stats.total_detections));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_fps), mp_obj_new_float(stats.fps));
    return dict;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(rtsmart_web_get_stats_obj, rtsmart_web_get_stats);

STATIC const mp_rom_map_elem_t rtsmart_web_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_rtsmart_web)},
    {MP_ROM_QSTR(MP_QSTR_push_frame), MP_ROM_PTR(&rtsmart_web_push_frame_obj)},
    {MP_ROM_QSTR(MP_QSTR_is_ready), MP_ROM_PTR(&rtsmart_web_is_ready_obj)},
    {MP_ROM_QSTR(MP_QSTR_get_control), MP_ROM_PTR(&rtsmart_web_get_control_obj)},
    {MP_ROM_QSTR(MP_QSTR_set_runtime), MP_ROM_PTR(&rtsmart_web_set_runtime_obj)},
    {MP_ROM_QSTR(MP_QSTR_set_stats), MP_ROM_PTR(&rtsmart_web_set_stats_obj)},
    {MP_ROM_QSTR(MP_QSTR_add_record), MP_ROM_PTR(&rtsmart_web_add_record_obj)},
    {MP_ROM_QSTR(MP_QSTR_delete_record), MP_ROM_PTR(&rtsmart_web_delete_record_obj)},
    {MP_ROM_QSTR(MP_QSTR_clear_records), MP_ROM_PTR(&rtsmart_web_clear_records_obj)},
    {MP_ROM_QSTR(MP_QSTR_get_stats), MP_ROM_PTR(&rtsmart_web_get_stats_obj)},
};
STATIC MP_DEFINE_CONST_DICT(rtsmart_web_module_globals, rtsmart_web_module_globals_table);

const mp_obj_module_t rtsmart_web_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&rtsmart_web_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_rtsmart_web, rtsmart_web_module);
