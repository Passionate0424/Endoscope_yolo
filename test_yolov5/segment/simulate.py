import os
import copy
import argparse
import numpy as np
import onnxruntime as ort
import nncase
import shutil
import math

def read_model_file(model_file):
    with open(model_file, 'rb') as f:
        model_content = f.read()
    return model_content

def cosine(gt, pred):
    return (gt @ pred) / (np.linalg.norm(gt, 2) * np.linalg.norm(pred, 2))

def main():
    parser = argparse.ArgumentParser(prog="nncase")
    parser.add_argument("--model", type=str,default="best.onnx", help='original model file')
    parser.add_argument("--model_input", type=str,default="onnx_input_float32.bin", help='input bin file for original model')
    parser.add_argument("--kmodel", type=str,default="best.kmodel", help='kmodel file')
    parser.add_argument("--kmodel_input", type=str,default="kmodel_input_uint8.bin", help='input bin file for kmodel')
    parser.add_argument("--input_width", type=int, default=320, help='input_width')
    parser.add_argument("--input_height", type=int, default=320, help='input_height')
    args = parser.parse_args()

    # cpu inference
    ort_session = ort.InferenceSession(args.model)
    output_names = []
    model_outputs = ort_session.get_outputs()
    for i in range(len(model_outputs)):
        output_names.append(model_outputs[i].name)
    model_input = ort_session.get_inputs()[0]
    model_input_name = model_input.name
    model_input_type = np.float32
    model_input_shape = model_input.shape
    model_input_data = np.fromfile(args.model_input, model_input_type).reshape(model_input_shape)
    cpu_results = []
    cpu_results = ort_session.run(output_names, { model_input_name : model_input_data })

    # create simulator
    sim = nncase.Simulator()
    # read kmodel
    kmodel = read_model_file(args.kmodel)
    # load kmodel
    sim.load_model(kmodel)
    # 更新参数为32倍数
    input_width = int(math.ceil(args.input_width / 32.0)) * 32
    input_height = int(math.ceil(args.input_height / 32.0)) * 32
    # read input.bin
    input_shape = [1, 3, input_height, input_width]
    dtype = sim.get_input_desc(0).dtype
    input = np.fromfile(args.kmodel_input, dtype).reshape(input_shape)
    # set input for simulator
    sim.set_input_tensor(0, nncase.RuntimeTensor.from_numpy(input))

    # simulator inference
    nncase_results = []
    sim.run()
    for i in range(sim.outputs_size):
        nncase_result = sim.get_output_tensor(i).to_numpy()
        # print("nncase_result:",nncase_result)
        # input_bin_file = 'output/output_{}.bin'.format(i,args.target)
        # nncase_result.tofile(input_bin_file)
        nncase_results.append(copy.deepcopy(nncase_result))

    # compare
    for i in range(sim.outputs_size):
        cos = cosine(np.reshape(nncase_results[i], (-1)), np.reshape(cpu_results[i], (-1)))
        print('output {0} cosine similarity : {1}'.format(i, cos))
    
    if os.path.exists("./gmodel_dump_dir"):
        shutil.rmtree("./gmodel_dump_dir")

if __name__ == '__main__':
    main()
