"""
scsp.py

Implements the Simple Core State Predictor.

Arguments are the following 
- <calling_interval_ns> specifies the periodicity of script execution.
- <idle_frequency_mhz> the frequency that is set in case the predicted state is idle.
- <confidence> represents the threshold of the confidence counter.

Example:
-s acaps_scsp:2000:1000:2

Core state values:
- RUNNING        0
- INITIALIZING   1
- STALLED        2
- SLEEPING       3
- WAKING_UP      4
- IDLE           5
- BROKEN         6
- NUM_STATES     7
"""

import sys, os, sim, acaps_csp as acsp, csv

class Scsp:

  def setup(self, args):
    self.events = []
    # args = args.split(':')
    args = dict(enumerate((args or '').split(':')))
                                             
    # Default calling interval 1 ms
    self.calling_interval_ns = int(args.get(0, None) or 1000000)

    # Default idle frequency 100 MHz
    self.idle_freq_mhz = int(args.get(1, None) or 1000)

    # Default confidence is 2
    self.predictor_confidence = int(args.get(2, None) or 2)

    self.dvfs_table = self.build_dvfs_table(int(sim.config.get('power/technology_node')))

    self.flag = False
    sim.util.Every(self.calling_interval_ns * sim.util.Time.NS, self.periodic, roi_only = True)

    self.num_cores = sim.config.ncores

    self.config_freq_mhz = int(float(sim.config.get('perf_model/core/frequency'))*1e+3)

    self.acsp = {}
    self.avg_core_frequency = {}
    self.avg_core_frequency_cont = {}

    # For each core create an predictor
    for i in range(0, self.num_cores):
      self.acsp[i] = acsp.Csp(history_size=1, conf_th = self.predictor_confidence)
      self.avg_core_frequency[i] = 0.0
      self.avg_core_frequency_cont[i] = 0.0

    self.results_folder = sim.config.output_dir
    self.stats_file = sim.config.output_dir + "acaps_scsp_stats.csv"
    self.res_file = sim.config.output_dir + "acaps_scsp_res.csv"

    print("[ACAPS_SCSP] Calling interval [ns]: " + str(self.calling_interval_ns))
    print("[ACAPS_SCSP] Idle freq. [MHz]: " + str(self.idle_freq_mhz))
    print("[ACAPS_SCSP] Predictor confidence: " + str(self.predictor_confidence))

    # Check if the file exists, and delete it if it does
    if os.path.exists(self.stats_file):
        os.remove(self.stats_file)

    with open(self.stats_file, 'w') as csvfile:
      # Create a CSV writer object
      csv_writer = csv.writer(csvfile)
      
      # Write the header to the CSV file
      header = ["Time", "Core" , "Actual State", "Predicted State"]
      csv_writer.writerow(header)

  def append_stats(self, data):
    # Append data to an existing CSV file
    with open(self.stats_file, 'a', ) as csvfile:
        # Create a CSV writer object
        csv_writer = csv.writer(csvfile)
        
        # Write the data to the CSV file
        csv_writer.writerow(data)
  
  def adjust_frequency(self, core, state):
      new_freq = None
      
      # If the current state is IDLE
      if (state == 5):
        new_freq = self.idle_freq_mhz
      else:
        new_freq = self.config_freq_mhz

      actual_freq = sim.dvfs.get_frequency(core)

      if (actual_freq != new_freq):
        sim.dvfs.set_frequency(core, new_freq)

  def periodic(self, time, time_delta):
    # Don't do anythin on the first call 
    if time_delta == 0:
      return

    for core in range(0, self.num_cores):
      actual_state = sim.dvfs.get_core_state(core)
      
      
      

        

        

     

  def build_dvfs_table(self, tech):
    # Build a table of (frequency, voltage) pairs.
    # Frequencies should be from high to low, and end with zero (or the lowest possible frequency)
    if tech == 22:
      return [ (2000, 1.0), (1800, 0.9), (1500, 0.8), (1000, 0.7), (0, 0.6) ]
    elif tech == 45:
      return [ (2000, 1.2), (1800, 1.1), (1500, 1.0), (1000, 0.9), (0, 0.8) ]
    else:
      raise ValueError('No DVFS table available for %d nm technology node' % tech)
    
  def get_vdd_from_freq(self, f):
    # Assume self.dvfs_table is sorted from highest frequency to lowest
    for _f, _v in self.dvfs_table:
      if f >= _f:
        return _v
    assert ValueError('Could not find a Vdd for invalid frequency %f' % f)

  def power(self):
    outputbase = os.path.join(self.results_folder, 'dvfs_power')

    freq = [ self.avg_core_frequency[core] for core in range(sim.config.ncores) ]
    vdd = [ self.get_vdd_from_freq(f) for f in freq ]
    
    configfile = outputbase+'.cfg'
    cfg = open(configfile, 'w')
    cfg.write('''
[perf_model/core]
frequency[] = %s
[power]
vdd[] = %s
    ''' % (','.join(map(lambda f: '%f' % (f / 1000.), freq)), ','.join(map(str, vdd))))
    cfg.close()

    os.system('unset PYTHONHOME; %s -d %s -o %s -c %s --no-graph --no-text' % (
      os.path.join(os.getenv('SNIPER_ROOT'), 'tools/mcpat.py'),
      sim.config.output_dir,
      outputbase,
      configfile,
    ))

  def hook_sim_end(self):
    # Check if the file exists, and delete it if it does
    if os.path.exists(self.res_file):
        os.remove(self.res_file)

    with open(self.res_file, 'w') as csvfile:
      # Create a CSV writer object
      csv_writer = csv.writer(csvfile)
      
      # Write the header to the CSV file
      header = ["Core", "Correct", "Incorrect", "Accuracy" ,"Avg. Freq. [MHz]"]
      csv_writer.writerow(header)

      for core in range(0, self.num_cores):
        predictor = self.acsp[core]
        stats = predictor.get_stats()
        avg_core_freq = int(self.avg_core_frequency[core])

        if (stats["Correct"] > 0):
          accuracy = (stats["Correct"] / (stats["Incorrect"] + stats["Correct"])) * 100.0
        else:
          accuracy = 0
        row = [core, stats["Correct"], stats["Incorrect"], accuracy, avg_core_freq]
        csv_writer.writerow(row)
    
    self.power()

sim.util.register(Scsp())
