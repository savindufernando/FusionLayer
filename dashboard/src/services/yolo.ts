import * as tf from '@tensorflow/tfjs';
import ort from 'onnxruntime-web';

export interface YoloPrediction {
    bbox: [number, number, number, number]; // [x, y, width, height] in original video dimensions
    class: string;
    score: number;
}

export class YoloEdgeModel {
    private model: ort.InferenceSession | null = null;
    private labels: string[] = [];

    // 122 Sri Lankan traffic sign classes from the synthetic dataset
    private defaultLabels = [
        'end_of_motorway', 'expressway', 'motorway', 'exit_ramp', 'caravan_site', 'cul_de_sac', 'emergency_telephone',
        'end_of_living_street', 'first_aid', 'hospital', 'light_refreshment', 'living_street', 'one_way_street',
        'parking', 'pedestrian_crossing', 'petrol_station', 'restaurant', 'swimming_pool', 'telephone', 'youth_hostel',
        'beginning_of_an_administrative_area', 'confirming_distances', 'direction_sign', 'light_signals_for_pedestrians',
        '5.00_am___9.00_pm_(supplementing_a_regulatory_sign)', 'school_(supplementing_a_regulatory_sign)',
        'pass_onto_left', 'pass_onto_right', 'proceed_straight', 'roundabout', 'turn_left_ahead', 'turn_left',
        'turn_right_ahead', 'turn_right', 'end_of_priority_road', 'give_way_to_oncoming_traffic', 'give_way',
        'priority_over_oncoming_traffic', 'priority_road', 'stop', 'all_vehicles_prohibited', 'maximum_length',
        'minimum_safe_distance', 'no_animal_drawn_vehicles', 'no_bicycles', 'no_entry', 'no_handcarts', 'no_horns',
        'no_left_turn', 'no_mopeds', 'no_motor_vehicles,_except_motorcycles', 'no_motor_vehicles', 'no_motorcycles',
        'no_overtaking_by_trucks', 'no_overtaking', 'no_parking_and_standing', 'no_parking_on_even_numbered_days',
        'no_parking_on_odd_numbered_days', 'no_parking', 'no_pedestrians', 'no_right_turn', 'no_tractors',
        'no_trailers_2', 'no_trailers', 'no_trucks', 'no_u_turn', 'height_limit',
        'maximum_speed_limit_(3_wheelers_and_land_vehicles_in_built_up_and_non_built_up_areas)',
        'maximum_speed_limit_(all_vehicles_within_school_areas_and_hospitals)',
        'maximum_speed_limit_(heavy_vehicles_in_non_built_up_areas)',
        'maximum_speed_limit_(light_vehicles_outside_built_up_areas)',
        'maximum_speed_limit_(vehicles_within_built_up_areas_except_for_3_wheelers_and_land_vehicles)',
        'maximum_speed_limit_ends', 'weight_limit_on_one_axle', 'weight_limit', 'width_limit', 'cycle_crossing',
        'overtaking_line', 'warning_line', 'green_traffic_light', 'red_&_yellow_traffic_light', 'red_traffic_light',
        'yellow_traffic_light', 'accident', 'animals', 'bump', 'children', 'curve_to_left', 'curve_to_right',
        'cyclists', 'dip', 'double_curve,_first_to_left', 'double_curve,_first_to_right', 'drawbridge',
        'falling_rocks', 'fog', 'give_way_ahead', 'intersection_with_a_secondary_road',
        'intersection_with_a_side_road_at_right_angles', 'joining_a_side_road_at_right_angles_to_the_left',
        'joining_a_side_road_at_right_angles_to_the_right', 'level_crossing_with_barriers_ahead',
        'level_crossing_without_barriers_ahead', 'loose_gravel', 'multi_track_level_crossing', 'other_dangers',
        'quayside_or_riverbank', 'road_narrows_on_left_side', 'road_narrows_on_right_side', 'road_narrows',
        'roadworks', 'single_track_level_crossing', 'slippery_road', 'soft_verges', 'steep_ascent', 'steep_descent',
        'stop_sign_ahead', 'traffic_light', 'tunnel', 'two_way_traffic', 'uneven_road', 'wild_animals'
    ];

    async load(modelUrl: string = '/model/best.onnx', labels: string[] = []) {
        await tf.ready();
        
        try {
            // Some Vite environments need ort.default.env
            const ortInstance = ort.env ? ort : (ort as any).default;
            if (ortInstance && ortInstance.env) {
                // Pin EXACTLY to the version installed (1.26.0) to avoid mismatch, 
                // and use CDN to completely bypass Vite's local dynamic import interception
                ortInstance.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.26.0/dist/';
            }
            
            this.model = await ortInstance.InferenceSession.create(modelUrl, { executionProviders: ['wasm'] });
            this.labels = labels.length > 0 ? labels : this.defaultLabels;
            console.log("YOLOv8 Edge Model (ONNX) loaded successfully");
        } catch (error) {
            console.error("Failed to load YOLOv8 ONNX model:", error);
            throw error; // Rethrow to let DashcamFeed handle it
        }
    }

    async detect(video: HTMLVideoElement): Promise<YoloPrediction[]> {
        if (!this.model) return [];

        const predictions: YoloPrediction[] = [];

        try {
            const inputSize = 320;
            const origWidth = video.videoWidth;
            const origHeight = video.videoHeight;
            
            // 1. Preprocessing (Synchronous part wrapped in tf.tidy)
            const inputData = tf.tidy(() => {
                const img = tf.browser.fromPixels(video);
                
                const maxDim = Math.max(origWidth, origHeight);
                const padY = maxDim - origHeight;
                const padX = maxDim - origWidth;
                
                const paddedImg = tf.pad(img, [[0, padY], [0, padX], [0, 0]]);
                const resized = tf.image.resizeBilinear(paddedImg, [inputSize, inputSize]);
                const normalized = resized.div(255.0).expandDims(0); 
                
                const nchw = normalized.transpose([0, 3, 1, 2]); 
                return nchw.dataSync(); // Use dataSync to keep it synchronous inside tidy
            });
            
            const ortInstance = ort.Tensor ? ort : (ort as any).default;
            const tensor = new ortInstance.Tensor('float32', Float32Array.from(inputData), [1, 3, inputSize, inputSize]);
            const inputName = this.model.inputNames[0];
            const outputName = this.model.outputNames[0];
            const feeds = { [inputName]: tensor };
            
            // 2. ONNX Inference (Asynchronous)
            const output = await this.model.run(feeds);
            const outTensorData = output[outputName].data as Float32Array;

            // 3. Postprocessing
            // We use tf.tidy for tensor operations, but NMS is async.
            // So we extract nmsBoxes and maxScores out of tidy.
            const { nmsBoxesArray, maxScoresArray, classIndicesArray } = tf.tidy(() => {
                const res = tf.tensor3d(outTensorData, [1, 126, 2100]);
                
                const transposed = res.transpose([0, 2, 1]); 
                const squeezed = transposed.squeeze([0]); 
                
                const boxesData = squeezed.slice([0, 0], [-1, 4]); 
                const scoresData = squeezed.slice([0, 4], [-1, -1]); 

                const w = boxesData.slice([0, 2], [-1, 1]);
                const h = boxesData.slice([0, 3], [-1, 1]);
                const cx = boxesData.slice([0, 0], [-1, 1]);
                const cy = boxesData.slice([0, 1], [-1, 1]);

                const x1 = cx.sub(w.div(2));
                const y1 = cy.sub(h.div(2));
                const x2 = cx.add(w.div(2));
                const y2 = cy.add(h.div(2));

                const nmsBoxes = tf.concat([y1, x1, y2, x2], 1); 
                const maxScores = scoresData.max(1); 
                const classIndices = scoresData.argMax(1); 
                
                return {
                    nmsBoxesArray: nmsBoxes.arraySync() as number[][],
                    maxScoresArray: maxScores.arraySync() as number[],
                    classIndicesArray: classIndices.arraySync() as number[]
                };
            });
            
            const confidenceThreshold = 0.15;
            
            // Convert back to tensors for NMS (these must be manually disposed)
            const nmsBoxesTensor = tf.tensor2d(nmsBoxesArray);
            const maxScoresTensor = tf.tensor1d(maxScoresArray);
            
            const nmsIndices = await tf.image.nonMaxSuppressionAsync(
                nmsBoxesTensor,
                maxScoresTensor,
                20, 
                0.45, 
                confidenceThreshold 
            );

            // Get arrays
            const indicesData = await nmsIndices.data();
            
            // Clean up the manual tensors
            tf.dispose([nmsBoxesTensor, maxScoresTensor, nmsIndices]);

            const maxDim = Math.max(origWidth, origHeight);
            const scale = maxDim / inputSize;

            for (let i = 0; i < indicesData.length; i++) {
                const idx = indicesData[i];
                
                const [by1, bx1, by2, bx2] = nmsBoxesArray[idx];
                
                const origX1 = bx1 * scale;
                const origY1 = by1 * scale;
                const origX2 = bx2 * scale;
                const origY2 = by2 * scale;

                if (origX1 >= origWidth || origY1 >= origHeight) continue;

                const finalX1 = Math.max(0, origX1);
                const finalY1 = Math.max(0, origY1);
                const finalW = Math.min(origX2 - finalX1, origWidth - finalX1);
                const finalH = Math.min(origY2 - finalY1, origHeight - finalY1);

                const classIdx = classIndicesArray[idx];
                const className = classIdx < this.labels.length ? this.labels[classIdx] : `class_${classIdx}`;

                predictions.push({
                    bbox: [finalX1, finalY1, finalW, finalH],
                    class: className,
                    score: maxScoresArray[idx]
                });
            }
            
        } catch (error) {
            console.error("YOLOv8 Detection Error (ONNX):", error);
            throw error; // Let DashcamFeed see it
        }

        return predictions;
    }
}
